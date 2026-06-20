#!/bin/bash
# Give the station (libusb) read/write access to ALL connected UVC cameras'
# raw USB nodes. Handles one OR multiple cameras of any make.
# Fixes: usbvideo "Failed to open device ... -3" / "has no available formats".
# Run with:  sudo bash /mnt/d/normacore/fix-camera.sh
#
# NOTE: a camera must first be attached to WSL from Windows PowerShell:
#   usbipd list                       (find the camera's BUSID)
#   usbipd bind   --busid <busid>
#   usbipd attach --wsl --busid <busid>
# Then run this script (or it auto-applies on next plug via the udev rule).
#
# SCOPE: this fixes camera ACCESS (libuvc can open the device). It does NOT fix
# frame CORRUPTION ("Failed to decode JPEG") seen when libuvc streams over
# usbip/WSL — that is a separate isochronous-bandwidth issue (use native Linux,
# or lower the capture resolution). See station_mcp/README.md.

echo "[1/4] Writing persistent udev rule for USB cameras..."
tee /etc/udev/rules.d/99-norma-camera.rules >/dev/null <<'EOF'
# NormaCore: let libusb open UVC webcams (raw /dev/bus/usb node needs rw).
# Generic: ANY USB device exposing a Video Class (UVC, class 0e) interface.
SUBSYSTEM=="usb", ENV{ID_USB_INTERFACES}=="*:0e????:*", MODE="0666"
# Belt-and-suspenders specific entries (common arm/webcam models):
SUBSYSTEM=="usb", ATTR{idVendor}=="046d", MODE="0666"
EOF

echo "[2/4] Reloading + retriggering udev..."
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --action=add
sleep 1

echo "[3/4] Granting access to every currently-connected camera now..."
count=0
for dev in /sys/bus/usb/devices/[0-9]*; do
  case "$dev" in *:*) continue;; esac          # skip interface entries
  isvideo=0
  for ifc in "$dev"/*:*; do
    [ -f "$ifc/bInterfaceClass" ] || continue
    [ "$(cat "$ifc/bInterfaceClass" 2>/dev/null)" = "0e" ] && isvideo=1
  done
  [ "$isvideo" = 1 ] || continue
  busnum=$(cat "$dev/busnum" 2>/dev/null); devnum=$(cat "$dev/devnum" 2>/dev/null)
  [ -n "$busnum" ] && [ -n "$devnum" ] || continue
  node=$(printf "/dev/bus/usb/%03d/%03d" "$busnum" "$devnum")
  if chmod 666 "$node" 2>/dev/null; then
    count=$((count+1))
    echo "  camera #$count: $node  ->  $(cat $dev/manufacturer 2>/dev/null) $(cat $dev/product 2>/dev/null) [$(cat $dev/idVendor):$(cat $dev/idProduct)]"
  fi
done

echo "[4/4] Found and enabled $count camera(s)."
if [ "$count" -lt 2 ]; then
  echo "  If you expected more, attach the other camera from Windows PowerShell:"
  echo "    usbipd list ; usbipd bind --busid <id> ; usbipd attach --wsl --busid <id>"
  echo "  then re-run this script (or it auto-applies on plug)."
fi
echo "The station picks up cameras within ~1s (it retries automatically)."
