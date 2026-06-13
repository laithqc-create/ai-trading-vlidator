#!/usr/bin/env python3
"""
Unit tests for auth utilities — no database required
"""

import json
from auth.utils import (
    hash_password, verify_password,
    generate_all_tokens, create_access_token, decode_access_token
)

def test_password_hashing():
    """Test password hashing and verification"""
    print("\n" + "="*70)
    print("TEST: Password Hashing & Verification")
    print("="*70)
    
    password = "SecurePassword123!"
    hash_val = hash_password(password)
    
    print(f"✓ Hashed password: {hash_val[:30]}...")
    print(f"  Hash length: {len(hash_val)} chars")
    
    # Test correct password
    if verify_password(password, hash_val):
        print(f"✓ Correct password accepted")
    else:
        print(f"✗ Correct password rejected")
        return False
    
    # Test incorrect password
    if not verify_password("WrongPassword", hash_val):
        print(f"✓ Incorrect password rejected")
    else:
        print(f"✗ Incorrect password accepted")
        return False
    
    return True

def test_token_generation():
    """Test token generation"""
    print("\n" + "="*70)
    print("TEST: Token Generation")
    print("="*70)
    
    tokens = generate_all_tokens()
    
    expected_keys = [
        "atv_api_token",
        "indicator_webhook_token",
        "ea_webhook_token",
        "screenshot_webhook_token"
    ]
    
    print(f"✓ Generated {len(tokens)} tokens:")
    for key, val in tokens.items():
        print(f"  - {key}: {val[:15]}... (len={len(val)})")
    
    # Verify all keys exist
    if set(tokens.keys()) == set(expected_keys):
        print(f"✓ All token keys present")
    else:
        print(f"✗ Missing or extra token keys")
        return False
    
    # Verify tokens are unique
    values = list(tokens.values())
    if len(set(values)) == len(values):
        print(f"✓ All tokens are unique")
    else:
        print(f"✗ Duplicate tokens detected")
        return False
    
    # Verify all tokens have expected format
    for key, val in tokens.items():
        if not val or len(val) < 20:
            print(f"✗ Token {key} too short: {val}")
            return False
    
    print(f"✓ All tokens have valid length")
    return True

def test_jwt_creation():
    """Test JWT token creation and decoding"""
    print("\n" + "="*70)
    print("TEST: JWT Creation & Decoding")
    print("="*70)
    
    user_id = 42
    jwt = create_access_token(user_id=user_id)
    
    print(f"✓ Created JWT: {jwt[:40]}...")
    print(f"  Length: {len(jwt)} chars")
    
    # Decode and verify
    decoded = decode_access_token(jwt)
    
    if not decoded:
        print(f"✗ Failed to decode JWT")
        return False
    
    print(f"✓ JWT decoded successfully")
    print(f"  Subject (user_id): {decoded.get('sub')}")
    print(f"  Issued at: {decoded.get('iat')}")
    print(f"  Expires at: {decoded.get('exp')}")
    
    # Verify user_id
    if decoded.get('sub') == str(user_id):
        print(f"✓ User ID matches: {user_id}")
    else:
        print(f"✗ User ID mismatch: expected {user_id}, got {decoded.get('sub')}")
        return False
    
    return True

def test_response_structure():
    """Test auth response structure"""
    print("\n" + "="*70)
    print("TEST: Auth Response Structure")
    print("="*70)
    
    # Simulate /auth/register response
    tokens = generate_all_tokens()
    jwt = create_access_token(user_id=1)
    
    response = {
        "ok": True,
        "access_token": jwt,
        "token_type": "bearer",
        "user": {
            "id": 1,
            "email": "test@example.com",
            "full_name": "Test User",
            "plan": "free",
            "created_at": "2026-06-13T18:40:00Z",
            "billing": {
                "name": "Test User",
                "company": None,
                "address": None,
                "city": None,
                "state": None,
                "zip": None,
                "country": None,
            },
            "tokens": {
                "api": tokens["atv_api_token"],
                "indicator": tokens["indicator_webhook_token"],
                "ea": tokens["ea_webhook_token"],
                "screenshot": tokens["screenshot_webhook_token"],
            }
        }
    }
    
    # Test JSON serialization
    try:
        json_str = json.dumps(response)
        parsed = json.loads(json_str)
        print(f"✓ Response JSON serializes correctly")
        print(f"  Size: {len(json_str)} bytes")
    except Exception as e:
        print(f"✗ JSON serialization failed: {e}")
        return False
    
    # Verify frontend can access tokens
    try:
        api_token = parsed['user']['tokens']['api']
        print(f"✓ Frontend can access tokens")
        print(f"  api token: {api_token[:15]}...")
    except Exception as e:
        print(f"✗ Failed to access tokens: {e}")
        return False
    
    # Verify localStorage compatibility
    try:
        localStorage_data = {
            "atv_jwt": parsed['access_token'],
            "atv_token": parsed['user']['tokens']['api'],
            "atv_user": json.dumps(parsed['user']),
        }
        print(f"✓ Data can be stored in localStorage")
        for key in localStorage_data:
            print(f"  {key}: {len(localStorage_data[key])} chars")
    except Exception as e:
        print(f"✗ localStorage preparation failed: {e}")
        return False
    
    return True

def test_multiple_token_generations():
    """Test that multiple token generations produce different tokens"""
    print("\n" + "="*70)
    print("TEST: Token Uniqueness Across Multiple Generations")
    print("="*70)
    
    # Generate tokens 3 times
    all_tokens = []
    for i in range(3):
        tokens = generate_all_tokens()
        all_tokens.append(tokens)
    
    # Compare
    for i in range(len(all_tokens)):
        for j in range(i + 1, len(all_tokens)):
            for key in all_tokens[i]:
                if all_tokens[i][key] == all_tokens[j][key]:
                    print(f"✗ Duplicate token found: {key}")
                    print(f"  Generation {i}: {all_tokens[i][key]}")
                    print(f"  Generation {j}: {all_tokens[j][key]}")
                    return False
    
    print(f"✓ Generated 3 sets of tokens, all unique")
    print(f"  Total tokens tested: {len(all_tokens) * len(all_tokens[0])}")
    
    return True

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("ATV AUTH UTILITIES TEST SUITE")
    print("="*70)
    
    tests = [
        ("Password Hashing", test_password_hashing),
        ("Token Generation", test_token_generation),
        ("JWT Creation", test_jwt_creation),
        ("Response Structure", test_response_structure),
        ("Token Uniqueness", test_multiple_token_generations),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - Auth system is working correctly!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    exit(main())
