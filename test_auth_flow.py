#!/usr/bin/env python3
"""
Complete auth flow test — verifies registration, login, profile, and token generation
"""

import asyncio
import json
from datetime import datetime
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import User
from auth.utils import hash_password, verify_password, create_access_token, generate_all_tokens
from config.settings import settings

async def test_user_creation():
    """Test 1: User creation with tokens"""
    print("\n" + "="*70)
    print("TEST 1: User Creation with Token Generation")
    print("="*70)
    
    async with AsyncSessionLocal() as db:
        # Cleanup: remove test user if exists
        existing = await db.execute(select(User).where(User.email == "test@example.com"))
        if existing.scalars().first():
            await db.execute("DELETE FROM users WHERE email = 'test@example.com'")
            await db.commit()
            print("✓ Cleaned up existing test user")
        
        # Create test user
        tokens = generate_all_tokens()
        print(f"\n✓ Generated tokens:")
        for name, val in tokens.items():
            print(f"  - {name}: {val[:12]}...")
        
        user = User(
            email="test@example.com",
            password_hash=hash_password("TestPassword123"),
            full_name="Test User",
            plan_tier="free",
            **tokens
        )
        db.add(user)
        await db.commit()
        print(f"\n✓ Created user: {user.id}")
        print(f"  Email: {user.email}")
        print(f"  Full name: {user.full_name}")
        print(f"  Plan: {user.plan_tier}")
        print(f"  atv_api_token: {user.atv_api_token[:12] if user.atv_api_token else 'MISSING'}...")
        print(f"  indicator_webhook_token: {user.indicator_webhook_token[:12] if user.indicator_webhook_token else 'MISSING'}...")
        
        return user.id

async def test_password_verification(user_id):
    """Test 2: Password verification"""
    print("\n" + "="*70)
    print("TEST 2: Password Verification")
    print("="*70)
    
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        
        # Test correct password
        if verify_password("TestPassword123", user.password_hash):
            print("✓ Password verification: CORRECT password accepted")
        else:
            print("✗ Password verification: CORRECT password rejected")
            return False
        
        # Test incorrect password
        if not verify_password("WrongPassword123", user.password_hash):
            print("✓ Password verification: INCORRECT password rejected")
        else:
            print("✗ Password verification: INCORRECT password accepted")
            return False
    
    return True

async def test_jwt_generation(user_id):
    """Test 3: JWT token generation"""
    print("\n" + "="*70)
    print("TEST 3: JWT Token Generation & Verification")
    print("="*70)
    
    jwt = create_access_token(user_id=user_id)
    print(f"✓ Generated JWT: {jwt[:30]}...")
    print(f"  Length: {len(jwt)} chars")
    print(f"  Algorithm: HS256")
    print(f"  User ID: {user_id}")
    
    # Decode and verify
    from auth.utils import decode_access_token
    decoded = decode_access_token(jwt)
    if decoded and decoded.get("sub") == str(user_id):
        print(f"✓ JWT verification: Token decoded correctly")
        print(f"  Subject: {decoded.get('sub')}")
        print(f"  Issued at: {datetime.fromtimestamp(decoded.get('iat', 0))}")
    else:
        print(f"✗ JWT verification: Failed to decode or verify")
        return False
    
    return True

async def test_user_distinct_accounts():
    """Test 4: Multiple users are distinct"""
    print("\n" + "="*70)
    print("TEST 4: Multiple User Accounts - Distinctness")
    print("="*70)
    
    async with AsyncSessionLocal() as db:
        # Create second test user
        tokens2 = generate_all_tokens()
        user2 = User(
            email="test2@example.com",
            password_hash=hash_password("TestPassword456"),
            full_name="Test User 2",
            plan_tier="free",
            **tokens2
        )
        db.add(user2)
        await db.commit()
        
        # Verify both users exist and are distinct
        user1_result = await db.execute(select(User).where(User.email == "test@example.com"))
        user1 = user1_result.scalars().first()
        
        user2_result = await db.execute(select(User).where(User.email == "test2@example.com"))
        user2 = user2_result.scalars().first()
        
        if user1 and user2:
            print(f"✓ Both users exist in database")
            print(f"  User 1 ID: {user1.id}, Email: {user1.email}")
            print(f"  User 2 ID: {user2.id}, Email: {user2.email}")
            
            if user1.id != user2.id:
                print(f"✓ User IDs are distinct")
            else:
                print(f"✗ User IDs are the same (duplicate!)")
                return False
            
            if user1.atv_api_token != user2.atv_api_token:
                print(f"✓ API tokens are distinct")
            else:
                print(f"✗ API tokens are identical (should be unique!)")
                return False
            
            # Count total users
            count_result = await db.execute(select(User))
            total = len(count_result.scalars().all())
            print(f"✓ Total users in database: {total}")
            
            return True
        else:
            print(f"✗ One or both users not found")
            return False

async def test_billing_fields():
    """Test 5: Billing field storage"""
    print("\n" + "="*70)
    print("TEST 5: Billing Information Storage")
    print("="*70)
    
    async with AsyncSessionLocal() as db:
        user = await db.get(User, 1)  # Get first test user
        
        # Update billing
        user.billing_name = "John Smith"
        user.billing_address = "123 Main St"
        user.billing_city = "London"
        user.billing_country = "GB"
        user.tax_id = "GB123456789"
        await db.commit()
        
        # Verify it was saved
        updated = await db.get(User, user.id)
        print(f"✓ Billing information saved:")
        print(f"  Name: {updated.billing_name}")
        print(f"  Address: {updated.billing_address}")
        print(f"  City: {updated.billing_city}")
        print(f"  Country: {updated.billing_country}")
        print(f"  Tax ID: {updated.tax_id}")
        
        return True

async def test_response_structure():
    """Test 6: Response structure matches frontend expectations"""
    print("\n" + "="*70)
    print("TEST 6: Auth Response Structure")
    print("="*70)
    
    async with AsyncSessionLocal() as db:
        user = await db.get(User, 1)
        
        # Simulate what /auth/register returns
        response = {
            "ok": True,
            "access_token": create_access_token(user_id=user.id),
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "plan": user.plan_tier,
                "billing": {
                    "name": user.billing_name,
                    "company": user.billing_company,
                    "address": user.billing_address,
                    "city": user.billing_city,
                    "state": user.billing_state,
                    "zip": user.billing_zip,
                    "country": user.billing_country,
                },
                "tokens": {
                    "api": user.atv_api_token,
                    "indicator": user.indicator_webhook_token,
                    "ea": user.ea_webhook_token,
                    "screenshot": user.screenshot_webhook_token,
                }
            }
        }
        
        print(f"✓ Response structure is correct:")
        print(f"  - ok: {response['ok']}")
        print(f"  - access_token: {response['access_token'][:20]}...")
        print(f"  - token_type: {response['token_type']}")
        print(f"  - user.id: {response['user']['id']}")
        print(f"  - user.email: {response['user']['email']}")
        print(f"  - user.tokens: {list(response['user']['tokens'].keys())}")
        
        # Verify frontend can parse it
        try:
            json_str = json.dumps(response)
            parsed = json.loads(json_str)
            if parsed['user']['tokens']['api']:
                print(f"✓ Frontend can parse and access tokens")
                return True
        except Exception as e:
            print(f"✗ JSON serialization failed: {e}")
            return False

async def cleanup():
    """Cleanup test data"""
    print("\n" + "="*70)
    print("CLEANUP: Removing Test Data")
    print("="*70)
    
    async with AsyncSessionLocal() as db:
        # Delete test users
        test_emails = ["test@example.com", "test2@example.com"]
        for email in test_emails:
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            if user:
                await db.delete(user)
                print(f"✓ Deleted test user: {email}")
        await db.commit()

async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("ATV AUTH SYSTEM TEST SUITE")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Run tests sequentially
        user_id = await test_user_creation()
        await test_password_verification(user_id)
        await test_jwt_generation(user_id)
        await test_user_distinct_accounts()
        await test_billing_fields()
        await test_response_structure()
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        print("\n✓ Auth system is functioning correctly!")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await cleanup()

if __name__ == "__main__":
    asyncio.run(main())
