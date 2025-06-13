# PPE Violation Detection System

A comprehensive AI-powered solution for detecting Personal Protective Equipment (PPE) violations in workplace environments. This system provides real-time monitoring, multi-source camera support, and pre-entry screening capabilities to ensure workplace safety compliance.

## 🚀 Key Features

### 1. **Real-time PPE Violation Detection**
- Automated detection of PPE compliance using YOLOv5 AI model
- Identifies missing or improperly worn safety equipment
- Supports detection of: Hard Hats, Safety Vests, Face Masks, and more
- Real-time alerts and notifications for violations

### 2. **Multi-Source Dashboard**
- Monitor multiple camera feeds simultaneously
- Interactive timeline visualization of violations across all sources
- Real-time compliance metrics and statistics
- Support for both video files and live streams (RTSP, HTTP)

### 3. **PPE Screening Station**
- Pre-entry safety compliance checks
- Live webcam or image upload options
- Auto-completion when all required PPE is detected
- Employee tracking and site-specific requirements

### 4. **Smart Alert System**
- Email notifications for violations and screening results
- Intelligent alert grouping to prevent spam
- Configurable recipients and thresholds

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [System Architecture](#system-architecture)
- [Features in Detail](#features-in-detail)
  - [Multi-Source Dashboard](#multi-source-dashboard)
  - [PPE Screening Station](#ppe-screening-station)
  - [Detection Capabilities](#detection-capabilities)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Contributing](#contributing)
- [License](#license)

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- Webcam (for screening station)
- CUDA-capable GPU (recommended for better performance)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ppe-violation-detection.git
cd ppe-violation-detection
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Download the PPE detection model:
   - Place the `ppe.pt` YOLOv5 model file in the `detection/` directory

4. Configure email settings (optional):
   - Update email credentials in `send_mail.py` for alert notifications

## 🏃‍♂️ Quick Start

1. Start the application:
```bash
python app.py
```

2. Open your browser and navigate to:
   - **Dashboard**: `http://localhost:5001/`
   - **PPE Screening**: `http://localhost:5001/screening`
   - **Legacy View**: `http://localhost:5001/legacy`

3. Add camera sources from the dashboard or start a screening session

## 🏗️ System Architecture

### Core Components

1. **Flask Web Application** (`app.py`)
   - RESTful API endpoints
   - WebSocket support for real-time updates
   - Multi-threaded source processing

2. **Detection Engine** (`detection/ppe_detector.py`)
   - YOLOv5-based object detection
   - Supports multiple PPE classes
   - Configurable confidence thresholds

3. **Frontend Interfaces**
   - Modern dashboard with real-time updates
   - Interactive screening station
   - Responsive design with glass morphism UI

### Threading Model
- Each camera source runs in separate threads:
  - Frame capture thread
  - Detection processing thread
- Background detection runs continuously
- Event queue for real-time distribution

## 📱 Features in Detail

### Multi-Source Dashboard

Access at: `http://localhost:5001/`

#### Key Features:
- **Real-time Timeline**: Visual representation of violations across all sources
- **Source Management**: Add/remove video files or live streams
- **Interactive Violations**: Click timeline dots for detailed information
- **Statistics Cards**:
  - Active Sources
  - Active Violations
  - Compliance Rate
  - Last Detection
- **Time Range Selection**: View last 5 min, 15 min, 30 min, or 1 hour
- **Export Capability**: Download detection data as JSON

#### Adding Sources:
1. Click "Add Source"
2. Select type (Video File or Live Stream)
3. Choose file or enter stream URL
4. Optionally name the source
5. Detection starts automatically

### PPE Screening Station

Access at: `http://localhost:5001/screening`

#### Screening Options:

**1. Live Webcam Screening:**
- Real-time PPE detection
- Position guidance for optimal detection
- Auto-completes when all PPE detected

**2. Image Upload:**
- Quick compliance check
- Instant results
- Perfect for pre-arrival verification

#### Required PPE (Configurable):
- Hard Hat (Required)
- Safety Vest (Required)
- Face Mask (Optional)

#### Features:
- Employee ID tracking
- Site-specific requirements
- Screening history logging
- Manager email notifications
- Smooth, real-time video feed

### Detection Capabilities

The system detects the following classes:
- **PPE Items**: Hardhat, Safety Vest, Mask
- **Violations**: NO-Hardhat, NO-Safety Vest, NO-Mask
- **Other**: Person, Safety Cone, machinery, vehicle

#### Violation Types:
- Missing PPE (worker without required equipment)
- Improper wearing (detected but not correctly worn)
- Zone violations (PPE requirements for specific areas)

## 📡 API Reference

### Dashboard APIs

```
GET /api/sources              # List all camera sources
POST /api/sources             # Add new source
DELETE /api/sources/<id>      # Remove source
POST /api/settings            # Update settings
GET /events                   # Server-sent events stream
```

### Screening APIs

```
GET /api/screening/sites              # Get available sites
GET /api/screening/requirements       # Get PPE requirements
POST /api/screening/detect            # Run detection on image
POST /api/screening/check-position    # Check positioning
POST /api/screening/complete          # Log screening result
```

### Video Streams

```
GET /source_video_raw/<source_id>       # Raw video feed
GET /source_video_processed/<source_id>  # Processed feed with detections
```

## ⚙️ Configuration

### Detection Settings
Modify confidence thresholds and detection parameters:

```python
# In app.py
default_confidence = 0.5  # Adjust detection sensitivity
```

### PPE Requirements
Customize screening requirements in `app.py`:

```python
requirements = [
    {"id": "hardhat", "name": "Hard Hat", "required": True},
    {"id": "safety-vest", "name": "Safety Vest", "required": True},
    # Add more as needed
]
```

### Email Alerts
Configure email settings for notifications:
- Set recipient email in dashboard settings
- Update SMTP credentials in `send_mail.py`

## 🔧 Advanced Features

### Performance Optimization
- Frame buffer management (60 frames max)
- Automatic cleanup of old detection events (>1 hour)
- Configurable detection intervals
- GPU acceleration support

### Compliance Tracking
- Frame-based compliance calculation
- Per-source violation statistics
- Historical data retention
- Export capabilities for reporting

### Extensibility
- Modular detector architecture
- Easy to add new PPE types
- Customizable alert rules
- API-first design for integration

## 🚦 Usage Examples

### Monitor Construction Site
```python
# Add RTSP camera stream
POST /api/sources
{
    "name": "Main Gate Camera",
    "type": "stream", 
    "path": "rtsp://192.168.1.100/stream"
}
```

### Quick PPE Check
1. Navigate to `/screening`
2. Enter employee ID
3. Upload photo or use webcam
4. System auto-completes on success

## 🐛 Troubleshooting

### Common Issues:

**Camera not detected:**
- Check webcam permissions in browser
- Ensure HTTPS or localhost access

**Detection not working:**
- Verify `ppe.pt` model is in `detection/` folder
- Check GPU drivers if using CUDA
- Adjust confidence threshold if needed

**Email alerts not sending:**
- Verify SMTP settings in `send_mail.py`
- Check firewall/network settings

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

### Areas for Contribution:
- Additional PPE types detection
- Mobile app development
- Integration with access control systems
- Multi-language support
- Performance optimizations

## 📄 License

This project is licensed under the [LICENSE] - see the LICENSE file for details.

## 🙏 Acknowledgments

- YOLOv5 by Ultralytics for the detection framework
- OpenCV community for computer vision tools
- Flask community for the web framework

---

**Note**: This system is designed to assist with safety compliance but should not replace human supervision and safety protocols. Always follow your organization's safety guidelines.

