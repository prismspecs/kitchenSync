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

---

get desktop bsackground from USB to work (might already?)

---

have the Pi download the video to disk from the USB for faster playback