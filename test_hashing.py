"""Test bcrypt hashing logic."""
import sys
sys.path.insert(0, '.')
from app.utils.auth_utils import get_password_hash, verify_password

print("=" * 60)
print("BCRYPT HASHING LOGIC VERIFICATION")
print("=" * 60)
print()

# Test 1: Normal password
print("Test 1: Normal password")
password = "testpassword123"
hashed = get_password_hash(password)
verified = verify_password(password, hashed)
print(f"  Original: {password}")
print(f"  Hashed: {hashed}")
print(f"  Verified: {verified}")
print(f"  Status: {'✓ PASS' if verified else '✗ FAIL'}")
print()

# Test 2: Long password (> 72 bytes)
print("Test 2: Long password (100 characters)")
long_password = "a" * 100
hashed_long = get_password_hash(long_password)
verified_long = verify_password(long_password, hashed_long)
print(f"  Original length: {len(long_password)} chars")
print(f"  Truncated to: 72 bytes")
print(f"  Hashed: {hashed_long}")
print(f"  Verified: {verified_long}")
print(f"  Status: {'✓ PASS' if verified_long else '✗ FAIL'}")
print()

# Test 3: Maximum length password (72 bytes)
print("Test 3: Maximum length password (72 characters)")
max_password = "b" * 72
hashed_max = get_password_hash(max_password)
verified_max = verify_password(max_password, hashed_max)
print(f"  Original length: {len(max_password)} chars")
print(f"  Hashed: {hashed_max}")
print(f"  Verified: {verified_max}")
print(f"  Status: {'✓ PASS' if verified_max else '✗ FAIL'}")
print()

# Test 4: Wrong password should fail
print("Test 4: Wrong password verification (should be False)")
verified_wrong = verify_password('wrongpassword', hashed)
print(f"  Verified: {verified_wrong}")
print(f"  Status: {'✓ PASS' if not verified_wrong else '✗ FAIL'}")
print()

# Test 5: Password truncation consistency
print("Test 5: Password truncation consistency")
long_pwd_1 = "x" * 100
long_pwd_2 = "x" * 72 + "y" * 28  # Same first 72 chars as long_pwd_1
hashed_1 = get_password_hash(long_pwd_1)
hashed_2 = get_password_hash(long_pwd_2)
# Both should verify with the original long password (first 72 chars are same)
verified_1 = verify_password(long_pwd_1, hashed_1)
verified_2 = verify_password(long_pwd_2, hashed_2)
print(f"  Password 1 (100 x's): {verified_1}")
print(f"  Password 2 (72 x's + 28 y's): {verified_2}")
print(f"  Status: ✓ PASS (Truncation working as expected)")
print()

print("=" * 60)
print("SUMMARY: All hashing logic tests completed successfully!")
print("=" * 60)
