"""
Quick test script to verify import summary modal functionality.
Run with: python manage.py shell < test_import_summary.py
"""
from django.test import Client
from django.contrib.auth import get_user_model
import io

User = get_user_model()

# Create test user
user, _ = User.objects.get_or_create(
    username='testadmin',
    defaults={'is_superuser': True, 'is_staff': True}
)
user.set_password('test123')
user.save()

# Create test client
client = Client()
client.force_login(user)

# Test 1: Import with valid data
print("\n=== Test 1: Import with valid CSV data ===")
csv_content = """Product / Service Name,Item Code (SKU),Item Type,Category,Unit,Item Cost,Item Selling Price
Test Widget A,TEST-A001,Finished Good,General,pcs,50.00,120.00
Test Widget B,TEST-B002,Raw Material,General,pcs,30.00,80.00"""

csv_file = io.BytesIO(csv_content.encode('utf-8'))
csv_file.name = 'test.csv'

response = client.post('/core/import/catalog/', {'csv_file': csv_file})
print(f"Status: {response.status_code}")
print(f"Response contains 'Import Summary': {'Import Summary' in response.content.decode()}")
print(f"Response contains 'Created': {'Created' in response.content.decode()}")
print(f"Response contains 'Successfully processed': {'Successfully processed' in response.content.decode()}")

# Test 2: Import with errors
print("\n=== Test 2: Import with errors (missing required field) ===")
csv_content_errors = """Product / Service Name,Item Code (SKU),Item Type,Category,Unit,Item Cost,Item Selling Price
Valid Item,VALID-001,Finished Good,General,pcs,100.00,200.00
Missing Code Item,,Finished Good,General,pcs,50.00,100.00
Another Valid,VALID-002,Raw Material,General,kg,75.00,150.00"""

csv_file2 = io.BytesIO(csv_content_errors.encode('utf-8'))
csv_file2.name = 'test_errors.csv'

response2 = client.post('/core/import/catalog/', {'csv_file': csv_file2})
print(f"Status: {response2.status_code}")
content = response2.content.decode()
print(f"Response contains 'Import Summary': {'Import Summary' in content}")
print(f"Response contains 'Failed Imports': {'Failed Imports' in content}")
print(f"Response contains 'Error Details': {'Error Details' in content}")
print(f"Response contains 'Created': {'Created' in content}")
print(f"Response contains success count: {'2' in content}")

print("\n=== All Tests Complete ===")
