// PPE Screening JavaScript
let webcamStream = null;
let detectionInterval = null;
let screeningActive = false;
let currentEmployeeId = null;
let currentSite = null;
let requiredPPE = [];
let detectedPPE = {};
let positionCheckInterval = null;
let autoCompleteTimeout = null;

// Default PPE requirements (configurable)
const defaultPPERequirements = [
	{ id: "hardhat", name: "Hard Hat", icon: "ri-shield-line", required: true },
	{
		id: "safety-vest",
		name: "Safety Vest",
		icon: "ri-shirt-line",
		required: true,
	},
];

// Initialize on page load
$(document).ready(function () {
	loadSites();
	loadPPERequirements();

	// Enter key handler for employee ID
	$("#employee-id").on("keypress", function (e) {
		if (e.which === 13) {
			startScreening();
		}
	});

	// Image upload handler
	$("#image-upload").on("change", handleImageUpload);
});

// Load available sites
function loadSites() {
	$.ajax({
		url: "/api/screening/sites",
		method: "GET",
		success: function (sites) {
			const select = $("#site-select");
			sites.forEach((site) => {
				select.append(`<option value="${site.id}">${site.name}</option>`);
			});
		},
		error: function () {
			// Use default sites if API fails
			const defaultSites = [
				{ id: "main-entrance", name: "Main Entrance" },
				{ id: "warehouse-a", name: "Warehouse A" },
				{ id: "construction-site-1", name: "Construction Site 1" },
			];
			const select = $("#site-select");
			defaultSites.forEach((site) => {
				select.append(`<option value="${site.id}">${site.name}</option>`);
			});
		},
	});
}

// Load PPE requirements
function loadPPERequirements() {
	$.ajax({
		url: "/api/screening/requirements",
		method: "GET",
		success: function (requirements) {
			requiredPPE = requirements;
		},
		error: function () {
			// Use default requirements if API fails
			requiredPPE = defaultPPERequirements;
		},
	});
}

// Start screening process
async function startScreening() {
	const employeeId = $("#employee-id").val().trim();
	const site = $("#site-select").val();

	if (!employeeId) {
		showNotification("Please enter Employee ID", "error");
		return;
	}

	if (!site) {
		showNotification("Please select a site", "error");
		return;
	}

	currentEmployeeId = employeeId;
	currentSite = site;

	// Initialize detection state
	detectedPPE = {};
	requiredPPE.forEach((item) => {
		detectedPPE[item.id] = false;
	});

	// Update UI
	$("#current-employee-id").text(employeeId);
	$("#current-site").text($("#site-select option:selected").text());

	// Switch views
	$("#employee-section").hide();
	$("#screening-section").show();

	// Populate checklist
	populateChecklist();

	// Start webcam
	try {
		await startWebcam();
		screeningActive = true;
		startDetection();
		startPositionCheck();
	} catch (error) {
		console.error("Failed to start webcam:", error);
		showNotification(
			"Failed to access webcam. Please check permissions.",
			"error"
		);
		cancelScreening();
	}
}

// Populate PPE checklist
function populateChecklist() {
	const checklist = $("#ppe-checklist");
	checklist.empty();

	requiredPPE.forEach((item) => {
		const checklistItem = $(`
            <div class="checklist-item" id="checklist-${item.id}">
                <div class="checklist-icon">
                    <i class="${item.icon}"></i>
                </div>
                <div class="checklist-content">
                    <h4>${item.name}</h4>
                    <p>${item.required ? "Required" : "Optional"}</p>
                </div>
                <div class="checklist-status">
                    <span>Checking...</span>
                </div>
            </div>
        `);
		checklist.append(checklistItem);
	});
}

// Start webcam
async function startWebcam() {
	const video = document.getElementById("webcam");

	const constraints = {
		video: {
			width: { ideal: 1280 },
			height: { ideal: 720 },
			facingMode: "user",
		},
		audio: false,
	};

	webcamStream = await navigator.mediaDevices.getUserMedia(constraints);
	video.srcObject = webcamStream;

	// Wait for video to be ready
	return new Promise((resolve) => {
		video.onloadedmetadata = () => {
			video.play();
			resolve();
		};
	});
}

// Start detection process
function startDetection() {
	const canvas = document.getElementById("detection-overlay");
	const ctx = canvas.getContext("2d");
	const video = document.getElementById("webcam");

	// Set canvas size to match video
	canvas.width = video.videoWidth;
	canvas.height = video.videoHeight;

	// Keep track of whether we're currently processing
	let processing = false;

	detectionInterval = setInterval(() => {
		if (screeningActive && !processing) {
			processing = true;

			// Create a temporary canvas for capturing the frame
			const tempCanvas = document.createElement("canvas");
			tempCanvas.width = video.videoWidth;
			tempCanvas.height = video.videoHeight;
			const tempCtx = tempCanvas.getContext("2d");

			// Capture frame to temporary canvas
			tempCtx.drawImage(video, 0, 0, tempCanvas.width, tempCanvas.height);
			const imageData = tempCanvas.toDataURL("image/jpeg", 0.8);

			// Send for detection
			$.ajax({
				url: "/api/screening/detect",
				method: "POST",
				contentType: "application/json",
				data: JSON.stringify({
					image: imageData,
					employee_id: currentEmployeeId,
				}),
				success: function (results) {
					processDetectionResults(results);
					processing = false;
				},
				error: function () {
					processing = false;
				},
			});
		}
	}, 500); // Run detection every 500ms for smoother experience
}

// Process detection results
function processDetectionResults(results) {
	console.log("=== Detection Results ===");
	console.log("All detections:", results.detections);

	// Update detected PPE state
	const newDetections = {};
	requiredPPE.forEach((item) => {
		newDetections[item.id] = false;
	});

	// Map detection classes to PPE items
	results.detections.forEach((detection) => {
		const className = detection.class;
		console.log(
			`Detection class: "${className}", confidence: ${detection.confidence}`
		);

		// Match exact class names from the model
		if (className === "Hardhat") {
			console.log("  -> Matched as Hardhat");
			newDetections["hardhat"] = true;
		}
		if (className === "Safety Vest") {
			console.log("  -> Matched as Safety Vest");
			newDetections["safety-vest"] = true;
		}
		// Also check for just "Safety" in case model outputs that
		if (className === "Safety") {
			console.log("  -> Found 'Safety' class, treating as Safety Vest");
			newDetections["safety-vest"] = true;
		}
	});

	console.log("Final detection state:", newDetections);

	// Update UI
	requiredPPE.forEach((item) => {
		const isDetected = newDetections[item.id];
		const checklistItem = $(`#checklist-${item.id}`);
		const statusText = checklistItem.find(".checklist-status span");

		if (isDetected !== detectedPPE[item.id]) {
			// State changed
			detectedPPE[item.id] = isDetected;

			if (isDetected) {
				checklistItem.removeClass("missing").addClass("detected");
				statusText.text("Detected").removeClass("missing").addClass("detected");
				checklistItem
					.find(".checklist-icon i")
					.removeClass()
					.addClass(item.icon);
			} else {
				checklistItem.removeClass("detected").addClass("missing");
				statusText
					.text("Not Detected")
					.removeClass("detected")
					.addClass("missing");
				checklistItem
					.find(".checklist-icon i")
					.removeClass()
					.addClass("ri-close-line");
			}
		}
	});

	// Update overall status
	updateScreeningStatus();

	// Draw bounding boxes
	drawDetections(results.detections);
}

// Draw detection bounding boxes
function drawDetections(detections) {
	const canvas = document.getElementById("detection-overlay");
	const ctx = canvas.getContext("2d");

	// Clear canvas completely for transparency
	ctx.clearRect(0, 0, canvas.width, canvas.height);

	// Draw each detection
	detections.forEach((detection) => {
		const [x1, y1, x2, y2] = detection.bbox;
		const label = detection.class;
		const confidence = detection.confidence;

		// Determine color based on type
		let color = "#3b82f6"; // Default blue
		if (label.startsWith("NO-")) {
			color = "#ef4444"; // Red for violations
		} else if (
			label === "Hardhat" ||
			label === "Safety Vest" ||
			label === "Safety" ||
			label === "Mask"
		) {
			color = "#22c55e"; // Green for PPE
		} else if (label === "Person") {
			color = "#3b82f6"; // Blue for person
		}

		// Draw bounding box with shadow for better visibility
		ctx.shadowColor = "rgba(0, 0, 0, 0.5)";
		ctx.shadowBlur = 4;
		ctx.strokeStyle = color;
		ctx.lineWidth = 3;
		ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

		// Draw label background
		ctx.shadowBlur = 0;
		ctx.fillStyle = color;
		const text = `${label} ${Math.round(confidence * 100)}%`;
		ctx.font = "16px Arial";
		const textWidth = ctx.measureText(text).width;
		ctx.fillRect(x1, y1 - 25, textWidth + 10, 25);

		// Draw label text
		ctx.fillStyle = "white";
		ctx.fillText(text, x1 + 5, y1 - 7);
	});
}

// Start position checking
function startPositionCheck() {
	const video = document.getElementById("webcam");
	const canvas = document.createElement("canvas");
	const ctx = canvas.getContext("2d");

	positionCheckInterval = setInterval(() => {
		if (screeningActive) {
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			ctx.drawImage(video, 0, 0);

			// Send for person detection
			const imageData = canvas.toDataURL("image/jpeg", 0.5);

			$.ajax({
				url: "/api/screening/check-position",
				method: "POST",
				contentType: "application/json",
				data: JSON.stringify({ image: imageData }),
				success: function (result) {
					updatePositionGuide(result);
				},
			});
		}
	}, 2000); // Check every 2 seconds
}

// Update position guide
function updatePositionGuide(result) {
	const guide = $("#guide-message");
	const guideText = guide.find("span");

	if (result.person_detected) {
		if (result.position_ok) {
			guide.removeClass("warning error").addClass("success");
			guideText.text("Perfect! Stay in position");
			setTimeout(() => {
				$("#positioning-guide").fadeOut();
			}, 2000);
		} else {
			guide.removeClass("success error").addClass("warning");
			guideText.text(result.message || "Please adjust your position");
			$("#positioning-guide").fadeIn();
		}
	} else {
		guide.removeClass("success warning").addClass("error");
		guideText.text("No person detected. Please step into view");
		$("#positioning-guide").fadeIn();
	}
}

// Update overall screening status
function updateScreeningStatus() {
	const allRequired = requiredPPE.filter((item) => item.required);
	const detectedRequired = allRequired.filter((item) => detectedPPE[item.id]);

	const passScreening = detectedRequired.length === allRequired.length;

	const resultDiv = $("#screening-result");
	const completeBtn = $("#complete-btn");

	if (passScreening) {
		resultDiv.removeClass("fail").addClass("pass").show();
		resultDiv.html(
			'<h3><i class="ri-check-circle-line"></i> All required PPE detected!</h3>'
		);
		completeBtn.prop("disabled", false);

		// Auto-complete after 2 seconds if all PPE is detected
		if (!autoCompleteTimeout && screeningActive) {
			autoCompleteTimeout = setTimeout(() => {
				if (passScreening && screeningActive) {
					showNotification(
						"All PPE detected! Completing screening...",
						"success"
					);
					completeScreening();
				}
			}, 2000);
		}
	} else {
		// Clear auto-complete timeout if PPE is no longer detected
		if (autoCompleteTimeout) {
			clearTimeout(autoCompleteTimeout);
			autoCompleteTimeout = null;
		}

		const missing = allRequired
			.filter((item) => !detectedPPE[item.id])
			.map((item) => item.name)
			.join(", ");
		resultDiv.removeClass("pass").addClass("fail").show();
		resultDiv.html(
			`<h3><i class="ri-alert-line"></i> Missing: ${missing}</h3>`
		);
		completeBtn.prop("disabled", true);
	}
}

// Complete screening
function completeScreening() {
	const allRequired = requiredPPE.filter((item) => item.required);
	const detectedRequired = allRequired.filter((item) => detectedPPE[item.id]);
	const passed = detectedRequired.length === allRequired.length;

	// Prepare screening data
	const screeningData = {
		employee_id: currentEmployeeId,
		site: currentSite,
		timestamp: new Date().toISOString(),
		passed: passed,
		detected_ppe: Object.keys(detectedPPE).filter((key) => detectedPPE[key]),
		missing_ppe: Object.keys(detectedPPE).filter(
			(key) =>
				!detectedPPE[key] && requiredPPE.find((p) => p.id === key)?.required
		),
		all_detections: detectedPPE,
	};

	// Submit screening result
	$.ajax({
		url: "/api/screening/complete",
		method: "POST",
		contentType: "application/json",
		data: JSON.stringify(screeningData),
		success: function (response) {
			showScreeningResult(passed, screeningData);
		},
		error: function () {
			showNotification("Failed to save screening result", "error");
		},
	});
}

// Show screening result modal
function showScreeningResult(passed, data) {
	const modal = $("#result-modal");
	const icon = $("#result-icon");
	const title = $("#result-title");
	const message = $("#result-message");
	const details = $("#result-details");

	// Stop screening
	stopScreening();

	if (passed) {
		icon
			.html('<i class="ri-check-circle-fill"></i>')
			.removeClass("fail")
			.addClass("pass");
		title.text("Screening Passed!");
		message.text("All required PPE detected. You may proceed to the site.");
	} else {
		icon
			.html('<i class="ri-close-circle-fill"></i>')
			.removeClass("pass")
			.addClass("fail");
		title.text("Screening Failed");
		message.text(
			"Missing required PPE. Please wear all required equipment and try again."
		);
	}

	// Show details
	details.html(`
        <div class="result-detail">
            <span class="result-detail-label">Employee ID:</span>
            <span class="result-detail-value">${data.employee_id}</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Site:</span>
            <span class="result-detail-value">${$(
							"#site-select option:selected"
						).text()}</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Time:</span>
            <span class="result-detail-value">${new Date().toLocaleString()}</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Detected PPE:</span>
            <span class="result-detail-value">${
							data.detected_ppe.join(", ") || "None"
						}</span>
        </div>
        ${
					data.missing_ppe.length > 0
						? `
        <div class="result-detail">
            <span class="result-detail-label">Missing PPE:</span>
            <span class="result-detail-value" style="color: var(--accent-red);">${data.missing_ppe.join(
							", "
						)}</span>
        </div>
        `
						: ""
				}
    `);

	modal.fadeIn();
}

// Stop screening
function stopScreening() {
	screeningActive = false;

	if (detectionInterval) {
		clearInterval(detectionInterval);
		detectionInterval = null;
	}

	if (positionCheckInterval) {
		clearInterval(positionCheckInterval);
		positionCheckInterval = null;
	}

	if (autoCompleteTimeout) {
		clearTimeout(autoCompleteTimeout);
		autoCompleteTimeout = null;
	}

	if (webcamStream) {
		webcamStream.getTracks().forEach((track) => track.stop());
		webcamStream = null;
	}
}

// Cancel screening
function cancelScreening() {
	stopScreening();
	$("#screening-section").hide();
	$("#employee-section").show();
	$("#employee-id").val("").focus();
}

// Reset for new screening
function resetScreening() {
	$("#result-modal").fadeOut();
	$("#image-detection-section").hide();
	cancelScreening();
}

// Show notification
function showNotification(message, type = "info") {
	const notification = $(`
        <div class="notification notification-${type}">
            <i class="ri-${getIconForType(type)} notification-icon"></i>
            <span>${message}</span>
        </div>
    `);

	$("body").append(notification);

	setTimeout(() => notification.addClass("show"), 10);

	setTimeout(() => {
		notification.removeClass("show");
		setTimeout(() => notification.remove(), 300);
	}, 4000);
}

function getIconForType(type) {
	const icons = {
		success: "check-line",
		error: "error-warning-line",
		warning: "alert-line",
		info: "information-line",
	};
	return icons[type] || icons.info;
}

// Handle image upload
function handleImageUpload(e) {
	const file = e.target.files[0];
	if (!file) return;

	// Validate file type
	if (!file.type.startsWith("image/")) {
		showNotification("Please select a valid image file", "error");
		return;
	}

	// Validate employee ID and site
	const employeeId = $("#employee-id").val().trim();
	const site = $("#site-select").val();

	if (!employeeId) {
		showNotification("Please enter Employee ID first", "error");
		$("#image-upload").val("");
		return;
	}

	if (!site) {
		showNotification("Please select a site first", "error");
		$("#image-upload").val("");
		return;
	}

	// Read and process image
	const reader = new FileReader();
	reader.onload = function (event) {
		// Process image for detection directly
		processUploadedImage(event.target.result, employeeId, site);
	};
	reader.readAsDataURL(file);
}

// Clear image upload
function clearImageUpload() {
	$("#image-upload").val("");
}

// Process uploaded image for PPE detection
function processUploadedImage(imageData, employeeId, site) {
	// Update UI for image detection
	currentEmployeeId = employeeId;
	currentSite = site;

	// Initialize detection state
	detectedPPE = {};
	requiredPPE.forEach((item) => {
		detectedPPE[item.id] = false;
	});

	// Update employee info
	$("#image-employee-id").text(employeeId);
	$("#image-site").text($("#site-select option:selected").text());

	// Show image detection section
	$("#employee-section").hide();
	$("#image-detection-section").show();

	// Set uploaded image
	$("#uploaded-image").attr("src", imageData);

	// Populate checklist for image detection
	populateImageChecklist();

	// Show processing status
	$("#processing-status").show();

	// Wait for image to load before processing
	$("#uploaded-image").on("load", function () {
		// Get image dimensions for overlay
		const img = this;
		const canvas = document.getElementById("image-detection-overlay");
		const ctx = canvas.getContext("2d");

		// Set canvas size to match image display size
		canvas.width = img.width;
		canvas.height = img.height;

		// Send for detection
		$.ajax({
			url: "/api/screening/detect",
			method: "POST",
			contentType: "application/json",
			data: JSON.stringify({
				image: imageData,
				employee_id: employeeId,
			}),
			success: function (results) {
				console.log("Detection results received:", results);

				// Hide processing status
				$("#processing-status").fadeOut();

				// Draw detection boxes on image
				drawImageDetections(results.detections, img);

				// Process detection results
				console.log("=== Image Detection Results ===");
				console.log("All detections:", results.detections);

				results.detections.forEach((detection) => {
					const className = detection.class;
					console.log(
						`Detection class: "${className}", confidence: ${detection.confidence}`
					);

					// Match exact class names from the model
					if (className === "Hardhat") {
						console.log("  -> Matched as Hardhat");
						detectedPPE["hardhat"] = true;
					}
					if (className === "Safety Vest") {
						console.log("  -> Matched as Safety Vest");
						detectedPPE["safety-vest"] = true;
					}
					// Also check for just "Safety" in case model outputs that
					if (className === "Safety") {
						console.log("  -> Found 'Safety' class, treating as Safety Vest");
						detectedPPE["safety-vest"] = true;
					}
				});

				console.log("Final detection state:", detectedPPE);

				// Update checklist UI
				updateImageChecklist();

				// Check if all required PPE is detected
				const allRequired = requiredPPE.filter((item) => item.required);
				const detectedRequired = allRequired.filter(
					(item) => detectedPPE[item.id]
				);
				const passed = detectedRequired.length === allRequired.length;

				// Show result
				const resultDiv = $("#image-screening-result");
				if (passed) {
					resultDiv.removeClass("fail").addClass("pass").show();
					resultDiv.html(
						'<h3><i class="ri-check-circle-line"></i> All required PPE detected!</h3>'
					);

					// Auto-complete after showing results for 2 seconds
					setTimeout(() => {
						showNotification(
							"All required PPE detected! Completing screening...",
							"success"
						);

						const screeningData = {
							employee_id: employeeId,
							site: site,
							timestamp: new Date().toISOString(),
							passed: true,
							detected_ppe: Object.keys(detectedPPE).filter(
								(key) => detectedPPE[key]
							),
							missing_ppe: [],
							all_detections: detectedPPE,
							method: "image_upload",
						};

						// Submit screening result
						$.ajax({
							url: "/api/screening/complete",
							method: "POST",
							contentType: "application/json",
							data: JSON.stringify(screeningData),
							success: function (response) {
								showImageUploadResult(true, screeningData);
							},
							error: function () {
								showNotification("Failed to save screening result", "error");
							},
						});
					}, 2000);
				} else {
					const missing = allRequired
						.filter((item) => !detectedPPE[item.id])
						.map((item) => item.name)
						.join(", ");
					resultDiv.removeClass("pass").addClass("fail").show();
					resultDiv.html(
						`<h3><i class="ri-alert-line"></i> Missing: ${missing}</h3>`
					);
				}
			},
			error: function () {
				$("#processing-status").fadeOut();
				showNotification("Failed to analyze image. Please try again.", "error");
				setTimeout(backToEmployeeSection, 2000);
			},
		});
	});
}

// Populate checklist for image detection
function populateImageChecklist() {
	const checklist = $("#image-ppe-checklist");
	checklist.empty();

	requiredPPE.forEach((item) => {
		const checklistItem = $(`
			<div class="checklist-item" id="image-checklist-${item.id}">
				<div class="checklist-icon">
					<i class="${item.icon}"></i>
				</div>
				<div class="checklist-content">
					<h4>${item.name}</h4>
					<p>${item.required ? "Required" : "Optional"}</p>
				</div>
				<div class="checklist-status">
					<span>Analyzing...</span>
				</div>
			</div>
		`);
		checklist.append(checklistItem);
	});
}

// Update image checklist based on detections
function updateImageChecklist() {
	requiredPPE.forEach((item) => {
		const isDetected = detectedPPE[item.id];
		const checklistItem = $(`#image-checklist-${item.id}`);
		const statusText = checklistItem.find(".checklist-status span");

		if (isDetected) {
			checklistItem.removeClass("missing").addClass("detected");
			statusText.text("Detected").removeClass("missing").addClass("detected");
			checklistItem.find(".checklist-icon i").removeClass().addClass(item.icon);
		} else {
			checklistItem.removeClass("detected").addClass("missing");
			statusText
				.text("Not Detected")
				.removeClass("detected")
				.addClass("missing");
			checklistItem
				.find(".checklist-icon i")
				.removeClass()
				.addClass("ri-close-line");
		}
	});
}

// Draw detection boxes on uploaded image
function drawImageDetections(detections, img) {
	const canvas = document.getElementById("image-detection-overlay");
	const ctx = canvas.getContext("2d");

	// Clear canvas
	ctx.clearRect(0, 0, canvas.width, canvas.height);

	// Calculate scale factors
	const scaleX = canvas.width / img.naturalWidth;
	const scaleY = canvas.height / img.naturalHeight;

	// Draw each detection
	detections.forEach((detection) => {
		const [x1, y1, x2, y2] = detection.bbox;
		const label = detection.class;
		const confidence = detection.confidence;

		// Scale coordinates
		const scaledX1 = x1 * scaleX;
		const scaledY1 = y1 * scaleY;
		const scaledX2 = x2 * scaleX;
		const scaledY2 = y2 * scaleY;

		// Determine color based on type
		let color = "#3b82f6"; // Default blue
		if (label.startsWith("NO-")) {
			color = "#ef4444"; // Red for violations
		} else if (
			label === "Hardhat" ||
			label === "Safety Vest" ||
			label === "Safety" ||
			label === "Mask"
		) {
			color = "#22c55e"; // Green for PPE
		} else if (label === "Person") {
			color = "#3b82f6"; // Blue for person
		}

		// Draw bounding box
		ctx.strokeStyle = color;
		ctx.lineWidth = 3;
		ctx.strokeRect(
			scaledX1,
			scaledY1,
			scaledX2 - scaledX1,
			scaledY2 - scaledY1
		);

		// Draw label background
		ctx.fillStyle = color;
		const text = `${label} ${Math.round(confidence * 100)}%`;
		ctx.font = "16px Arial";
		const textWidth = ctx.measureText(text).width;
		ctx.fillRect(scaledX1, scaledY1 - 25, textWidth + 10, 25);

		// Draw label text
		ctx.fillStyle = "white";
		ctx.fillText(text, scaledX1 + 5, scaledY1 - 7);
	});
}

// Back to employee section
function backToEmployeeSection() {
	$("#image-detection-section").hide();
	$("#employee-section").show();
	clearImageUpload();
}

// Switch to live screening
function switchToLiveScreening() {
	$("#image-detection-section").hide();
	startScreening();
}

// Show result for image upload
function showImageUploadResult(passed, data) {
	const modal = $("#result-modal");
	const icon = $("#result-icon");
	const title = $("#result-title");
	const message = $("#result-message");
	const details = $("#result-details");

	if (passed) {
		icon
			.html('<i class="ri-check-circle-fill"></i>')
			.removeClass("fail")
			.addClass("pass");
		title.text("Image Check Passed!");
		message.text(
			"All required PPE detected in the uploaded image. You may proceed to the site."
		);
	}

	// Show details
	details.html(`
        <div class="result-detail">
            <span class="result-detail-label">Employee ID:</span>
            <span class="result-detail-value">${data.employee_id}</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Site:</span>
            <span class="result-detail-value">${$(
							"#site-select option:selected"
						).text()}</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Time:</span>
            <span class="result-detail-value">${new Date().toLocaleString()}</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Method:</span>
            <span class="result-detail-value">Image Upload</span>
        </div>
        <div class="result-detail">
            <span class="result-detail-label">Detected PPE:</span>
            <span class="result-detail-value">${
							data.detected_ppe.join(", ") || "None"
						}</span>
        </div>
    `);

	modal.fadeIn();
	clearImageUpload();
}
