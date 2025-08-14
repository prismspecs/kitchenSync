+ should it seek slightly AHEAD of the leader, since the operation takes a sec?


seek_success = False
            try:
                # Method 1: Direct position set
...

it should not do this. it should just use whatever method works, preferably #1


collaborator should use the same playback engine, etc. (x11? wayland?) as the leader

---
for setup.sh...
# make the menu bar hide
in file .config/wf-panel-pi.ini ADD the following:
autohide=true
autohide_duration=500

then I would like to hide the desktop icons so edit
/etc/xdg/pcmanfm/LXDE-pi/desktop-items-0.conf 

to include
show_trash=0
show_mounts=0
wallpaper=
desktop_bg=#000000

note that wallpaper and desktop_bg are already set, but adding it to the end resets those values.

note that this only works if there is no file here so delete it
~/.config/pcmanfm/LXDE-pi/desktop-items-0.conf


---

getting openbox to work
sudo apt install openbox obconf xserver-xorg
sudo cp /usr/share/xsessions/openbox.desktop /usr/share/xsessions/openbox-session.desktop
sudo nano /etc/lightdm/lightdm.conf

add:

greeter-session=pi-greeter-labwc
user-session=LXDE-pi-labwc
autologin-user=kitchensync
autologin-session=LXDE-pi-labwc
display-setup-script=/usr/share/dispsetup.sh
user-session=openbox-session

