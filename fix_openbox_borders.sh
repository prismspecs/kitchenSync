#!/bin/bash
# fix_openbox_borders.sh - Automates removing window borders in Openbox

echo "Configuring Openbox for borderless fullscreen..."

# 1. Ensure config directory exists
mkdir -p ~/.config/openbox

# 2. Copy default config if it doesn't exist
if [ ! -f ~/.config/openbox/rc.xml ]; then
    echo "Copying default rc.xml..."
    cp /etc/xdg/openbox/rc.xml ~/.config/openbox/rc.xml
fi

# 3. Use python to cleanly insert the application rule before the end of the <applications> section
# This is safer than sed for XML files.
python3 - <<EOF
import os

config_path = os.path.expanduser("~/.config/openbox/rc.xml")
with open(config_path, 'r') as f:
    lines = f.readlines()

new_rule = [
    '  <application class="*">\n',
    '    <decor>no</decor>\n',
    '    <fullscreen>yes</fullscreen>\n',
    '  </application>\n'
]

# Check if rule already exists to avoid duplication
content = "".join(lines)
if '<decor>no</decor>' not in content:
    with open(config_path, 'w') as f:
        for line in lines:
            if '</applications>' in line:
                f.writelines(new_rule)
            f.write(line)
    echo_msg = "Added borderless rule to rc.xml"
else:
    echo_msg = "Borderless rule already exists in rc.xml"

print(echo_msg)
EOF

# 4. Reconfigure Openbox to apply changes
echo "Reconfiguring Openbox..."
DISPLAY=:0 openbox --reconfigure

echo "-----------------------------------------------"
echo "Done! Try your video command now."
echo "-----------------------------------------------"
