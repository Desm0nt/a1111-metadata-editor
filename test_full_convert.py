"""Test full conversion process"""
from comfy_converter import convert_comfy_to_a1111
import os

files = ['kotamota_00070.png', 'Dross_00146.png']

# Create copies to avoid modifying originals
import shutil
for f in files:
    copy_name = f.replace('.png', '_test.png')
    if os.path.exists(copy_name):
        os.remove(copy_name)
    shutil.copy(f, copy_name)
    
    print(f"\n{'='*60}")
    print(f"Converting {copy_name}...")
    result = convert_comfy_to_a1111(copy_name, backup=False)
    print(f"Result: {result}")
    
    # Verify the conversion
    from PIL import Image
    img = Image.open(copy_name)
    params = img.info.get('parameters', '')
    print(f"Parameters length: {len(params)}")
    print(f"Preview: {params[:200]}..." if params else "No parameters found!")
