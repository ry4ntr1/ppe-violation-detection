# Multi-Source PPE Detection Dashboard

This application has been upgraded to support multiple camera sources with a real-time detection timeline dashboard.

## New Features

### 1. **Multi-Source Dashboard** (`/dashboard`)
- Real-time timeline visualization showing detections across all camera sources
- Summary cards displaying:
  - Active Sources count
  - Active Violations count
  - Compliance Rate percentage
  - Last Detection timestamp
- Adjustable time range (5 min, 15 min, 30 min, 1 hour)
- Export timeline data to JSON

### 2. **Source Management**
- Add multiple video sources:
  - Video files from the uploads folder
  - Live streams (RTSP, HTTP, etc.)
- Each source runs independently in its own thread
- Real-time status monitoring (Active/Inactive)
- FPS tracking per source

### 3. **Individual Camera Views** (`/camera/<source_id>`)
- View both raw and AI-processed feeds for any source
- Real-time detection log with violation types and confidence scores
- Toggle between view modes (both feeds, raw only, processed only)
- Fullscreen support

### 4. **Real-Time Updates**
- Server-Sent Events (SSE) for live updates
- Detection events pushed to dashboard in real-time
- Automatic statistics updates every 5 seconds
- No page refresh required

### 5. **API Endpoints**
- `GET /api/sources` - List all sources
- `POST /api/sources` - Add a new source
- `DELETE /api/sources/<id>` - Remove a source
- `POST /api/settings` - Update app settings

## Usage

### Access the Dashboard
Navigate to `http://localhost:5001/` to access the multi-source dashboard.

### Add a Camera Source
1. Click "Add Source" button
2. Choose source type:
   - **Video File**: Select from uploaded videos
   - **Live Stream**: Enter stream URL (e.g., `rtsp://camera.local/stream`)
3. (Optional) Enter a descriptive name - if left blank, a name will be auto-generated based on the source
4. Click "Add Source"

### View Individual Camera
Click the "View" button on any source card to open the dedicated camera view with:
- Side-by-side raw and processed feeds
- Real-time detection log
- Toggle between view modes

### Configure Settings
Click the settings icon to:
- Set email alert recipient
- Enable/disable email alerts
- Adjust detection confidence threshold

### Export Timeline Data
Click "Export" in the timeline section to download detection data as JSON.

### Interactive Timeline
- **Clickable Violations**: Click on any violation dot in the timeline to see details
- **Violation Popup**: Shows:
  - Violation type
  - Exact timestamp
  - Source name
  - Confidence level
  - Frame number
  - Quick link to view the camera feed
- **Visual Indicators**: Different colors for different violation types:
  - Red: NO-Hardhat
  - Orange: NO-Mask  
  - Yellow: NO-Safety Vest

## Architecture

The multi-source system uses:
- **Threading**: Each source runs in separate threads for parallel processing
  - Frame processing thread: Reads frames from video source and maintains buffer
  - Detection processing thread: Runs AI detection continuously in background
- **Background Detection**: Detections run automatically when sources are added, even without viewing
- **Event Queue**: Detection events are queued for real-time distribution
- **SSE**: Server-Sent Events deliver updates to connected clients
- **Frame Buffers**: Per-source frame buffers for smooth playback

## Key Features Update

### Smart Alert System
- **Single Alert per Violation**: Email alerts are sent only once per violation instance (grouped by minute)
- **No Spam**: Prevents repeated alerts for the same violation
- **Alert Tracking**: Each source tracks which alerts have been sent

### Accurate Compliance Rate
- **Frame-based Calculation**: Compliance rate = (frames without violations / total frames) × 100
- **Real-time Updates**: Continuously updated as frames are processed
- **Per-source Tracking**: Each source maintains its own compliance metrics

### Background Detection Processing
- **Automatic Start**: Detection begins immediately when a source is added
- **Continuous Processing**: Runs independently of whether anyone is viewing the streams
- **Real-time Updates**: Timeline updates every second with new detections
- **Resource Efficient**: Small delays between detections to prevent CPU overload
- **Historical Data**: Last hour of detection events are stored and sent to new dashboard connections

### Performance Considerations
- Each source runs 2 threads: one for frame capture, one for detection
- Detection runs at a slightly lower rate than frame capture to conserve resources
- Frame buffers are limited to 60 frames to manage memory usage
- Detection events older than 1 hour are automatically cleaned up

## Legacy Support

The original single-source view is still available at `/legacy` for backward compatibility. 