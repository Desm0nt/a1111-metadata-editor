from comfy_converter import extract_comfy_prompts

files = ['kotamota_00070.png', 'Dross_00146.png']

for f in files:
    print(f"\n=== {f} ===")
    try:
        pos, neg = extract_comfy_prompts(f)
        if pos:
            print(f"Positive ({len(pos)} chars): {pos[:300]}...")
        else:
            print("Positive: None")
        print(f"Negative: {neg}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
