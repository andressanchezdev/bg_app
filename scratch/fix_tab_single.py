with open('ui/tab_single.py', 'rb') as f:
    data = f.read()

# Replace the snippet
old_part = b'if folder_name:\r\n                        destination_blob_name = f"{folder_name}/{filename}"\r\n                    else:\r\n                        destination_blob_name = filename'
if old_part not in data:
    old_part = b'if folder_name:\n                        destination_blob_name = f"{folder_name}/{filename}"\n                    else:\n                        destination_blob_name = filename'

new_part = b'destination_blob_name = filename'
assert old_part in data, "Snippet not found"
data = data.replace(old_part, new_part)

with open('ui/tab_single.py', 'wb') as f:
    f.write(data)
print("Successfully updated ui/tab_single.py")

