# PPE Detection Application - Deployment Guide

This guide covers deployment and migration to the optimized, refactored version of the PPE Detection Application.

## Performance Improvements

The refactored application includes the following optimizations:

### 1. **Modular Architecture**
- Separated concerns into dedicated service modules
- Better code organization for maintainability
- Reduced coupling between components

### 2. **Frame Processing Optimizations**
- Reduced frame buffer size from 60 to 30 frames (configurable)
- Intelligent frame skipping based on processing performance
- Frame optimization for detection (resizing large frames)
- Caching of detection results

### 3. **Detection Optimizations**
- Detection runs on separate threads per source
- Configurable frame skip rate (process every Nth frame)
- Duplicate detection removal using IOU
- Detector instance caching

### 4. **Email Service Improvements**
- Batch email processing to reduce email volume
- Rate limiting (10 emails per 5 minutes)
- Deduplication of alerts
- Configurable cooldown period

### 5. **Event System Optimization**
- Non-blocking event queue with size limits
- Efficient SSE client management
- Periodic stats updates instead of continuous

### 6. **Memory Management**
- Circular buffers with automatic cleanup
- Event retention limits
- Proper resource cleanup on shutdown

## Migration Guide

### Step 1: Backup Current Installation
```bash
# Backup current application
cp -r /path/to/ppe-violation-detection /path/to/backup/

# Backup any custom configurations
cp app.py app_original.py
```

### Step 2: Install New Files
```bash
# Copy new modules to your installation
cp config.py models.py utils.py /path/to/ppe-violation-detection/
cp -r services/ /path/to/ppe-violation-detection/
cp app_refactored.py /path/to/ppe-violation-detection/
```

### Step 3: Environment Configuration

Create a `.env` file or set environment variables:

```bash
# Application environment
export FLASK_ENV=production  # or development

# Performance tuning
export MAX_FRAME_BUFFER_SIZE=30
export DETECTION_FRAME_SKIP=3
export MAX_DETECTION_EVENTS=1000

# Email configuration
export EMAIL_ALERTS_ENABLED=true
export EMAIL_RECIPIENT=your-email@example.com
export EMAIL_COOLDOWN_SEC=60

# Advanced settings (optional)
export DETECTION_CACHE_SIZE=100
export CACHE_TTL_SECONDS=5
export MAX_WORKER_THREADS=4
```

### Step 4: Update Dependencies

No new dependencies are required, but ensure you have:
```bash
pip install --upgrade opencv-python numpy flask
```

### Step 5: Test the Refactored Version

1. Run the refactored version alongside the original:
```bash
# Terminal 1 - Original app (port 5000)
python app.py

# Terminal 2 - Refactored app (port 5001)
python app_refactored.py --port 5001
```

2. Compare performance metrics
3. Verify all features work correctly

### Step 6: Switch to Refactored Version

Once testing is complete:

```bash
# Rename files
mv app.py app_legacy.py
mv app_refactored.py app.py

# Restart your service
# For systemd:
sudo systemctl restart ppe-detection

# For Docker:
docker-compose restart

# For PM2:
pm2 restart ppe-detection
```

## Configuration Options

### Performance Tuning

| Setting | Default | Description | Impact |
|---------|---------|-------------|--------|
| `MAX_FRAME_BUFFER_SIZE` | 30 | Max frames in buffer | Memory usage |
| `DETECTION_FRAME_SKIP` | 3 | Process every Nth frame | CPU usage vs accuracy |
| `DETECTION_THREAD_SLEEP` | 0.033 | Sleep between detections | CPU usage |
| `DETECTION_CACHE_SIZE` | 100 | Cached detection results | Memory vs performance |

### Recommended Settings by Hardware

#### Low-end Hardware (Raspberry Pi, 2-4 cores)
```bash
export MAX_FRAME_BUFFER_SIZE=20
export DETECTION_FRAME_SKIP=5
export MAX_WORKER_THREADS=2
```

#### Mid-range Hardware (4-8 cores, 8GB RAM)
```bash
export MAX_FRAME_BUFFER_SIZE=30
export DETECTION_FRAME_SKIP=3
export MAX_WORKER_THREADS=4
```

#### High-end Hardware (8+ cores, 16GB+ RAM)
```bash
export MAX_FRAME_BUFFER_SIZE=40
export DETECTION_FRAME_SKIP=2
export MAX_WORKER_THREADS=8
```

## Monitoring Performance

### Built-in Metrics

The refactored app provides performance metrics via the API:

```bash
# Get detection statistics
curl http://localhost:5000/api/stats

# Monitor in real-time
watch -n 1 'curl -s http://localhost:5000/api/stats | jq .'
```

### Log Analysis

Enable detailed logging:
```python
# In config.py or environment
export LOG_LEVEL=INFO
```

Key metrics to monitor:
- Processing FPS per source
- Detection cache hit rate
- Event queue size
- Email queue size

### Performance Dashboard

Access the dashboard at `http://localhost:5000/dashboard` to see:
- Real-time FPS for each source
- Compliance rates
- Active violations
- System status

## Production Deployment

### Using Gunicorn (Recommended)

```bash
# Install gunicorn
pip install gunicorn

# Run with optimal settings
gunicorn -w 4 \
  -k gevent \
  --timeout 120 \
  --keep-alive 5 \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  -b 0.0.0.0:5000 \
  app:app
```

### Using Docker

Create a `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libopencv-dev \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

# Copy application
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Set production environment
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run with gunicorn
CMD ["gunicorn", "-w", "4", "-k", "gevent", "-b", "0.0.0.0:5000", "app:app"]
```

### Using PM2

```javascript
// ecosystem.config.js
module.exports = {
  apps: [{
    name: 'ppe-detection',
    script: 'app.py',
    interpreter: 'python3',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      FLASK_ENV: 'production',
      PORT: 5000
    }
  }]
};
```

## Troubleshooting

### High CPU Usage
1. Increase `DETECTION_FRAME_SKIP`
2. Reduce `MAX_FRAME_BUFFER_SIZE`
3. Lower video resolution in source

### High Memory Usage
1. Reduce `MAX_FRAME_BUFFER_SIZE`
2. Reduce `DETECTION_CACHE_SIZE`
3. Lower `MAX_DETECTION_EVENTS`

### Delayed Detections
1. Decrease `DETECTION_FRAME_SKIP`
2. Increase `MAX_WORKER_THREADS`
3. Optimize frame size

### Email Not Sending
1. Check rate limits in logs
2. Verify `EMAIL_ALERTS_ENABLED=true`
3. Check email service logs
4. Reduce `EMAIL_BATCH_SIZE` if needed

## Rollback Procedure

If issues occur, rollback to the original version:

```bash
# Stop current service
sudo systemctl stop ppe-detection

# Restore original files
mv app.py app_refactored_backup.py
mv app_legacy.py app.py

# Remove new modules (optional)
rm -rf services/ config.py models.py utils.py

# Restart service
sudo systemctl start ppe-detection
```

## Support

For issues or questions:
1. Check application logs: `tail -f app.log`
2. Review performance metrics
3. Verify environment configuration
4. Test with reduced load (fewer sources)

The refactored application maintains full backward compatibility while providing significant performance improvements and better maintainability. 