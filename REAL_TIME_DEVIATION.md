# Real-Time Deviation Monitoring

## What You'll See Now

When you run `python collaborator.py --debug`, you'll now get continuous deviation monitoring:

### Example Output:
```
✓ Debug mode: ENABLED (via command line)
✓ MIDI output initialized on port 0
Starting KitchenSync Collaborator 'pi-38417'
✅ Collaborator pi-38417 started successfully!
Collaborator ready. Waiting for time sync from leader...
🚀 Session started at 01:20:44
🎵 Started MIDI playback

📊 Sync: leader=5.230s → video=5.225s → deviation=-0.005s
📊 Sync: leader=7.430s → video=7.425s → deviation=-0.005s
📊 Sync: leader=9.630s → video=9.640s → deviation=+0.010s
🔄 Sync correction: 0.242s deviation
📊 Sync: leader=12.030s → video=12.025s → deviation=-0.005s
```

### Frequency Options
The monitoring appears every **0.2 seconds** (every 10 sync messages at 50Hz).

**To adjust frequency, change the modulo value:**
```python
# In _handle_sync method:
if self.sync_message_count % 10 == 0:  # Current: every 0.2s

# Other options:
if self.sync_message_count % 5 == 0:   # Every 0.1s (faster)
if self.sync_message_count % 25 == 0:  # Every 0.5s (slower)  
if self.sync_message_count % 50 == 0:  # Every 1.0s (slowest)
```

## What Each Value Means

**📊 Sync: leader=5.230s → video=5.225s → deviation=-0.005s**

- **leader=5.230s**: Time position the leader is broadcasting
- **video=5.225s**: Current position of this collaborator's video
- **deviation=-0.005s**: How far behind (-) or ahead (+) this collaborator is
  - Negative = collaborator is behind leader
  - Positive = collaborator is ahead of leader
  - Goal is to keep this close to 0.000s

## When Corrections Happen

The system will trigger a sync correction when the **median deviation** (filtered from multiple samples) exceeds the threshold (typically 0.2s).

**You'll see both:**
1. **Continuous monitoring**: Shows real-time deviation every 0.2s
2. **Correction events**: Shows when actual sync corrections are applied

This gives you complete visibility into how well the collaborator is staying in sync with the leader.

## Production vs Debug

- **Production mode**: Only shows correction events (🔄 Sync correction)
- **Debug mode**: Shows continuous monitoring (📊 Sync) + correction events

Now you can see exactly how the sync is performing in real-time!
