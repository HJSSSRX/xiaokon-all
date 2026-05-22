# -*- coding: utf-8 -*-
"""Explore Android E01 image - find partitions and extract databases"""
import sys, io, struct, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import pyewf

E01 = r"A:\检材 手机\24CS_Phone.E01"

def open_e01():
    filenames = pyewf.glob(E01)
    h = pyewf.handle()
    h.open(filenames)
    return h

def read_at(h, offset, size):
    h.seek(offset)
    return h.read(size)

def parse_mbr(h):
    """Parse MBR partition table"""
    mbr = read_at(h, 0, 512)
    parts = []
    for i in range(4):
        off = 446 + i * 16
        entry = mbr[off:off+16]
        status = entry[0]
        ptype = entry[4]
        lba_start = struct.unpack_from('<I', entry, 8)[0]
        lba_size = struct.unpack_from('<I', entry, 12)[0]
        if lba_size > 0:
            parts.append({
                'idx': i,
                'status': status,
                'type': ptype,
                'lba_start': lba_start,
                'lba_size': lba_size,
                'byte_start': lba_start * 512,
                'byte_size': lba_size * 512,
            })
    return parts

def main():
    h = open_e01()
    total = h.get_media_size()
    print(f"Image size: {total} bytes ({total/(1024**3):.2f} GB)")
    
    # Parse MBR
    parts = parse_mbr(h)
    print(f"\nMBR Partitions: {len(parts)}")
    for p in parts:
        ptype_name = {0x83: 'Linux', 0x82: 'Linux swap', 0x0c: 'FAT32', 0x07: 'NTFS',
                      0xee: 'GPT protective', 0x05: 'Extended', 0x0f: 'Extended LBA'}.get(p['type'], f"0x{p['type']:02x}")
        size_gb = p['byte_size'] / (1024**3)
        print(f"  P{p['idx']}: type={ptype_name} start=0x{p['byte_start']:x} ({p['lba_start']} sectors) size={size_gb:.2f} GB")
        
        # Read first bytes of partition to check filesystem
        data = read_at(h, p['byte_start'], 4096)
        # Check for ext4 superblock (at offset 1024 within partition)
        if len(data) >= 1080:
            magic = struct.unpack_from('<H', data, 1024 + 56)[0]
            if magic == 0xEF53:
                print(f"    -> ext4 filesystem detected!")
        # Check for sparse image
        if data[:4] == b'\x3a\xff\x26\xed':
            print(f"    -> Android sparse image")
        if data[:8] == b'ANDROID!':
            print(f"    -> Android boot image")
    
    # If no partitions found or only 1, scan for ext4 superblocks
    if len(parts) == 0:
        print("\nNo MBR partitions. Scanning for filesystem signatures...")
    
    # Scan for ext4 superblock magic at common offsets
    print("\nScanning for ext4 superblocks...")
    scan_offsets = [0, 512, 1024, 4096, 0x100000, 0x200000, 0x800000, 
                    0x1000000, 0x2000000, 0x4000000, 0x8000000, 0x10000000,
                    0x20000000, 0x40000000]
    
    for base in scan_offsets:
        if base + 2048 > total:
            break
        data = read_at(h, base, 2048)
        # ext4 superblock at offset 1024
        if len(data) >= 1080:
            magic = struct.unpack_from('<H', data, 1024 + 56)[0]
            if magic == 0xEF53:
                block_count = struct.unpack_from('<I', data, 1024 + 4)[0]
                block_size_log = struct.unpack_from('<I', data, 1024 + 24)[0]
                block_size = 1024 << block_size_log
                vol_name_bytes = data[1024+120:1024+136]
                vol_name = vol_name_bytes.split(b'\x00')[0].decode('utf-8', 'replace')
                fs_size = block_count * block_size
                print(f"  ext4 at 0x{base:x}: name='{vol_name}' size={fs_size/(1024**3):.2f} GB blocks={block_count} bsize={block_size}")
    
    # Also search for SQLite headers directly (brute force but effective)
    print("\nSearching for key Android data patterns...")
    CHUNK = 64 * 1024 * 1024  # 64MB chunks
    sqlite_magic = b'SQLite format 3\x00'
    
    offset = 0
    sqlite_locations = []
    while offset < total and len(sqlite_locations) < 200:
        data = read_at(h, offset, CHUNK)
        if not data:
            break
        pos = 0
        while pos < len(data) - 16:
            idx = data.find(sqlite_magic, pos)
            if idx < 0:
                break
            abs_offset = offset + idx
            # Read more context to identify the DB
            if idx + 200 < len(data):
                ctx = data[idx:idx+200]
            else:
                ctx = read_at(h, abs_offset, 200)
            # Try to get table names from SQLite header area
            sqlite_locations.append(abs_offset)
            pos = idx + 16
        offset += CHUNK - 256  # overlap
        if offset % (512 * 1024 * 1024) == 0:
            print(f"  Scanned {offset/(1024**3):.1f} GB, found {len(sqlite_locations)} SQLite DBs so far...")
    
    print(f"\nTotal SQLite databases found: {len(sqlite_locations)}")
    
    # For each SQLite, try to identify it
    print("\nIdentifying key databases...")
    for loc in sqlite_locations[:100]:
        # Read first 8KB of each SQLite
        data = read_at(h, loc, 8192)
        text = data.decode('latin-1', 'replace')
        
        # Look for identifiers
        identifiers = []
        if 'EnMicroMsg' in text or 'rcontact' in text or 'message' in text.lower():
            identifiers.append('WeChat')
        if 'contacts2' in text or 'raw_contacts' in text:
            identifiers.append('Contacts')
        if 'mmssms' in text or 'sms' in text.lower():
            identifiers.append('SMS')
        if 'browser' in text.lower() or 'bookmark' in text.lower():
            identifiers.append('Browser')
        if 'amap' in text.lower() or 'autonavi' in text.lower():
            identifiers.append('AMap/Gaode')
        if 'mijia' in text.lower() or 'xiaomi' in text.lower() or 'smarthome' in text.lower():
            identifiers.append('MiJia')
        if 'package' in text.lower() and 'install' in text.lower():
            identifiers.append('PackageManager')
        if 'gedatalk' in text.lower() or 'geda' in text.lower():
            identifiers.append('GeDa')
        
        if identifiers:
            # Try to get table names
            tables = []
            for t in ['CREATE TABLE', 'create table']:
                idx = 0
                while True:
                    idx = text.find(t, idx)
                    if idx < 0: break
                    end = text.find('(', idx)
                    if end > 0 and end - idx < 100:
                        tname = text[idx+len(t):end].strip().strip('"').strip("'").strip('`')
                        tables.append(tname)
                    idx += len(t)
            
            print(f"  0x{loc:x}: {', '.join(identifiers)} tables={tables[:5]}")
    
    h.close()

if __name__ == '__main__':
    main()
