# KitchenSync Synchronization Test Guide

This guide shows you how to test synchronization between KitchenSync leader and collaborator devices using a simple test script.

## Quick Test Setup

### 1. On Your Test Device (Any Computer)

The test script requires **no external dependencies** - it uses only Python standard library modules.

```bash
# Download the test script
# (Copy test_sync_listener.py to your test device)

# Make it executable (optional)
chmod +x test_sync_listener.py

# Run the test listener
python3 test_sync_listener.py
```

### 2. What the Test Script Does

The script listens on two UDP ports:
- **Port 5005**: Time synchronization broadcasts from the leader
- **Port 5006**: Control commands and system messages

It will display:
- ⏰ **SYNC messages**: Real-time time synchronization data
- 🎮 **COMMAND messages**: System control messages
- 📊 **STATUS updates**: Periodic summaries every 10 seconds
- 📍 **Local IP**: Your device's IP address for network troubleshooting

### 3. Expected Output

When the KitchenSync leader is running and broadcasting:

```
🎯 KitchenSync Test Listener
========================================
This script listens for KitchenSync leader broadcasts
to test synchronization between devices.

✅ Listening on ports 5005 (sync) and 5006 (control)
📍 Local IP: 192.168.1.100
🔍 Waiting for KitchenSync leader broadcasts...

🚀 Started listening for KitchenSync broadcasts
Press Ctrl+C to stop

⏰ [14:30:25.123] SYNC from 192.168.1.50:5005 (Leader: leader-001)
   🕐 Leader time: 15.234s
   📊 Total sync messages: 1

🎮 [14:30:25.456] COMMAND from 192.168.1.50:5006
   📝 Type: start
   📊 Total commands: 1
   🔑 action: start_playback
```

## Network Requirements

### Firewall Settings

Make sure your test device allows incoming UDP traffic on ports 5005 and 5006:

**macOS/Linux:**
```bash
# Check if ports are accessible
sudo netstat -an | grep :5005
sudo netstat -an | grep :5006
```

**Windows:**
- Check Windows Firewall settings
- Allow Python/your terminal through the firewall

### Network Configuration

- Both devices must be on the same network
- UDP broadcast packets must be allowed
- No special network configuration required for basic testing

## Troubleshooting

### No Messages Received

1. **Check network connectivity:**
   ```bash
   ping [LEADER_IP_ADDRESS]
   ```

2. **Verify ports are listening:**
   ```bash
   # On test device
   netstat -an | grep :5005
   netstat -an | grep :5006
   ```

3. **Check firewall settings** on both devices

4. **Verify leader is broadcasting:**
   - Check leader logs for broadcast activity
   - Ensure leader has started time sync broadcasting

### Port Already in Use

If you get "Address already in use" errors:

```bash
# Check what's using the ports
sudo lsof -i :5005
sudo lsof -i :5006

# Kill conflicting processes if needed
sudo kill -9 [PID]
```

## Advanced Testing

### Custom Port Testing

If your KitchenSync system uses different ports:

```python
# Modify the ports in the script
listener = KitchenSyncTestListener(sync_port=5007, control_port=5008)
```

### Network Capture

For deeper debugging, you can also use network tools:

```bash
# Capture UDP traffic (requires admin/root)
sudo tcpdump -i any udp port 5005 or udp port 5006

# Or use Wireshark with filter:
# udp.port == 5005 || udp.port == 5006
```

## What to Look For

### Successful Synchronization

- **Regular sync messages** every 100ms (default interval)
- **Consistent timing** between sync messages
- **Command messages** when leader starts/stops playback
- **Status updates** showing active communication

### Potential Issues

- **Missing sync messages**: Network connectivity or firewall issues
- **Irregular timing**: Network congestion or leader performance issues
- **No commands**: Leader not sending control messages
- **High latency**: Network performance issues

## Next Steps

Once you confirm the test script receives data:

1. **Test with actual collaborator Pi** to verify full system sync
2. **Monitor timing accuracy** between devices
3. **Test network resilience** by temporarily disconnecting devices
4. **Verify MIDI synchronization** on collaborator devices

The test script provides a foundation for debugging network communication issues before deploying the full KitchenSync system.
