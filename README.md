# PPE-Violation-Detection
PPE - Violation Detection using AI/ML Repository

This repository provides a comprehensive solution for detecting Personal Protective Equipment (PPE) violations using AI/ML techniques. With the increasing importance of workplace safety, it is crucial to ensure that individuals in hazardous environments are wearing the appropriate PPE. This project leverages the power of artificial intelligence and machine learning to automate the process of PPE detection and violation identification.

Key Features:
- PPE Detection: The repository includes pre-trained models and algorithms capable of detecting various types of PPE such as helmets, safety goggles, masks, gloves, and more. These models are designed to accurately identify the presence or absence of PPE in real-time images or video streams.
- Violation Identification: The system goes beyond PPE detection and extends to identifying violations. By analyzing the detected PPE, the models can determine if the PPE is being worn correctly or if any violations are present, such as incorrect positioning, improper fitting, or partial use of protective gear.
- Real-time Monitoring: The solution supports real-time monitoring of PPE compliance, allowing for immediate intervention when violations are detected. It provides visual feedback, alerts, and notifications to relevant stakeholders, enabling swift action to ensure safety protocols are followed.
- Customization and Integration: The codebase is designed to be easily customizable and extensible, allowing users to fine-tune the models to their specific requirements. Additionally, the repository provides integration examples with popular video processing libraries and frameworks, facilitating seamless incorporation into existing workflows.

Contributing to this Repository:
We welcome contributions from the community to enhance the PPE violation detection system. Whether you have improvements to the existing models, additional features, or new ideas to explore, your contributions are valuable. Please refer to our contribution guidelines and code of conduct for more information on how to get involved.

Getting Started:
To get started, please refer to the documentation and tutorials provided in this repository. They will guide you through the setup process, explain the usage of the pre-trained models, and demonstrate how to integrate the system into your own projects.

License:
This repository is released under the [LICENSE] and encourages open collaboration and innovation in the domain of PPE violation detection.

We believe that by combining the power of AI/ML with workplace safety, we can contribute to creating safer environments for individuals and foster a culture of adherence to PPE protocols. Join us in this mission by exploring, contributing, and utilizing the capabilities of this PPE - Violation Detection using AI/ML repository.

## Detector Usage

The application now uses a YOLOv5 model (`ppe.pt`) to detect common PPE and
workplace objects. The model is wrapped in a detector located in the
`detection/` package. You can enable or disable detectors when requesting the
processed video stream using the `detectors` query parameter. For example:

```
http://localhost:5000/video_processed?detectors=ppe
```

When no parameter is supplied all detectors are enabled. Currently the registry
contains the single `ppe` detector which reports the following classes:
`Hardhat`, `Mask`, `NO-Hardhat`, `NO-Mask`, `NO-Safety Vest`, `Person`,
`Safety Cone`, `Safety Vest`, `machinery` and `vehicle`.

