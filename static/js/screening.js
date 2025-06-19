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
let videoSource = null; // For video file playback

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
	loadPPEVideos();

	// Enter key handler for employee ID
	$("#employee-id").on("keypress", function (e) {
		if (e.which === 13) {
			startScreening();
		}
	});

	// Image upload handler
	$("#image-upload").on("change", handleImageUpload);

	// Video source change handler
	$("#video-source-select").on("change", function () {
		const selectedVideo = $(this).val();
		if (selectedVideo) {
			// Enable the start button
			$("#start-screening-btn").prop("disabled", false);
		}
	});
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

// Load PPE videos from static/ppe_videos/
function loadPPEVideos() {
	$.ajax({
		url: "/api/screening/ppe_videos",
		method: "GET",
		success: function (data) {
			const select = $("#video-source-select");
			select.empty();
			select.append('<option value="">Select a video source</option>');
			
			if (data.videos && data.videos.length > 0) {
				data.videos.forEach((video) => {
					select.append(`<option value="${video}">${video}</option>`);
				});
			} else {
				select.append('<option value="" disabled>No videos available</option>');
			}
		},
		error: function () {
			console.error("Failed to load PPE videos");
			const select = $("#video-source-select");
			select.html('<option value="" disabled>Failed to load videos</option>');
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
	const screeningType =
		$('input[name="screening-type"]:checked').val() || "webcam";
	const videoFile = $("#video-source-select").val();

	if (!employeeId) {
		showNotification("Please enter Employee ID", "error");
		return;
	}

	if (!site) {
		showNotification("Please select a site", "error");
		return;
	}

	if (screeningType === "video" && !videoFile) {
		showNotification("Please select a video source", "error");
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

	// Start appropriate source
	try {
		if (screeningType === "video") {
			await startVideoSource(videoFile);
		} else {
			await startWebcam();
		}
		screeningActive = true;
		startDetection();
		if (screeningType === "webcam") {
			startPositionCheck();
		}
	} catch (error) {
		console.error("Failed to start screening:", error);
		showNotification(
			screeningType === "video"
				? "Failed to load video. Please try another source."
				: "Failed to access webcam. Please check permissions.",
			"error"
		);
		cancelScreening();
	}
}

// Start video source
async function startVideoSource(videoFile) {
	const video = document.getElementById("webcam");
	
	// Set video source
	video.src = `/static/ppe_videos/${videoFile}`;
	video.loop = true;
	
	// Wait for video to be ready
	return new Promise((resolve, reject) => {
		video.onloadedmetadata = () => {
			video.play()
				.then(resolve)
				.catch(reject);
		};
		video.onerror = reject;
	});
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
		message.text("All required PPE has been detected successfully.");
	} else {
		icon
			.html('<i class="ri-close-circle-fill"></i>')
			.removeClass("pass")
			.addClass("fail");
		title.text("Screening Failed");
		message.text("Please ensure all required PPE is worn properly.");
	}

	// Build details
	const detailsHtml = `
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
			<span class="result-detail-label">PPE Detected:</span>
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
	`;
	details.html(detailsHtml);

	// Show modal
	modal.fadeIn(300);
}

function stopScreening() {
	screeningActive = false;

	// Stop detection
	if (detectionInterval) {
		clearInterval(detectionInterval);
		detectionInterval = null;
	}

	// Stop position check
	if (positionCheckInterval) {
		clearInterval(positionCheckInterval);
		positionCheckInterval = null;
	}

	// Clear auto-complete timeout
	if (autoCompleteTimeout) {
		clearTimeout(autoCompleteTimeout);
		autoCompleteTimeout = null;
	}

	// Stop webcam
	if (webcamStream) {
		webcamStream.getTracks().forEach((track) => track.stop());
		webcamStream = null;
	}

	// Stop video if playing
	const video = document.getElementById("webcam");
	if (video.src) {
		video.pause();
		video.src = "";
	}
}

function cancelScreening() {
	stopScreening();
	$("#screening-section").hide();
	$("#employee-section").show();
}

function resetScreening() {
	$("#result-modal").fadeOut(300);
	cancelScreening();
	// Clear form
	$("#employee-id").val("");
	$("#site-select").val("");
	$("#video-source-select").val("");
}

function showNotification(message, type = "info") {
	// Use the Apple UI notification system if available
	if (window.AppleUI) {
		window.AppleUI.showNotification({
			message: message,
			type: type,
		});
	} else {
		// Fallback to simple alert
		alert(message);
	}
}

function getIconForType(type) {
	const icons = {
		success: "check-circle-line",
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

	if (!file.type.startsWith("image/")) {
		showNotification("Please select an image file", "error");
		return;
	}

	const reader = new FileReader();
	reader.onload = function (event) {
		const imageData = event.target.result;

		// Get employee ID and site
		const employeeId = $("#employee-id").val().trim() || "Guest";
		const site = $("#site-select").val() || "main-entrance";

		// Process the uploaded image
		processUploadedImage(imageData, employeeId, site);
	};
	reader.readAsDataURL(file);
}

// Clear image upload
function clearImageUpload() {
	$("#image-upload").val("");
	$(".image-preview").remove();
}

// Process uploaded image
function processUploadedImage(imageData, employeeId, site) {
	currentEmployeeId = employeeId;
	currentSite = site;

	// Initialize detection state
	detectedPPE = {};
	requiredPPE.forEach((item) => {
		detectedPPE[item.id] = false;
	});

	// Update UI
	$("#image-employee-id").text(employeeId);
	$("#image-site").text(
		$("#site-select option:selected").text() || "Main Entrance"
	);

	// Switch views
	$("#employee-section").hide();
	$("#image-detection-section").show();

	// Display the image
	$("#uploaded-image").attr("src", imageData);

	// Populate checklist
	populateImageChecklist();

	// Show processing status
	$("#processing-status").show();

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
			// Process results
			processImageDetectionResults(results);

			// Hide processing status
			$("#processing-status").fadeOut();

			// Show result
			const allRequired = requiredPPE.filter((item) => item.required);
			const detectedRequired = allRequired.filter(
				(item) => detectedPPE[item.id]
			);
			const passed = detectedRequired.length === allRequired.length;

			showImageUploadResult(passed, {
				employee_id: employeeId,
				site: site,
				detected_ppe: Object.keys(detectedPPE).filter(
					(key) => detectedPPE[key]
				),
				missing_ppe: Object.keys(detectedPPE).filter(
					(key) =>
						!detectedPPE[key] && requiredPPE.find((p) => p.id === key)?.required
				),
			});
		},
		error: function () {
			$("#processing-status").fadeOut();
			showNotification("Failed to process image", "error");
		},
	});
}

function processImageDetectionResults(results) {
	// Update detected PPE state
	const newDetections = {};
	requiredPPE.forEach((item) => {
		newDetections[item.id] = false;
	});

	// Map detection classes to PPE items
	results.detections.forEach((detection) => {
		const className = detection.class;
		if (className === "Hardhat") {
			newDetections["hardhat"] = true;
		}
		if (className === "Safety Vest" || className === "Safety") {
			newDetections["safety-vest"] = true;
		}
	});

	// Update global state
	detectedPPE = newDetections;

	// Update checklist UI
	updateImageChecklist();

	// Draw detections on image
	const img = document.getElementById("uploaded-image");
	drawImageDetections(results.detections, img);
}

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
                    <span>Checking...</span>
                </div>
            </div>
        `);
		checklist.append(checklistItem);
	});
}

function updateImageChecklist() {
	requiredPPE.forEach((item) => {
		const isDetected = detectedPPE[item.id];
		const checklistItem = $(`#image-checklist-${item.id}`);
		const statusText = checklistItem.find(".checklist-status span");

		if (isDetected) {
			checklistItem.removeClass("missing").addClass("detected");
			statusText.text("Detected");
		} else {
			checklistItem.removeClass("detected").addClass("missing");
			statusText.text("Not Detected");
		}
	});
}

function drawImageDetections(detections, img) {
	const canvas = document.getElementById("image-detection-overlay");
	const ctx = canvas.getContext("2d");

	// Set canvas size to match image
	canvas.width = img.naturalWidth;
	canvas.height = img.naturalHeight;

	// Scale canvas to display size
	const scaleX = img.width / img.naturalWidth;
	const scaleY = img.height / img.naturalHeight;
	canvas.style.width = img.width + "px";
	canvas.style.height = img.height + "px";

	// Clear canvas
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
		} else if (["Hardhat", "Safety Vest", "Safety", "Mask"].includes(label)) {
			color = "#22c55e"; // Green for PPE
		}

		// Draw bounding box
		ctx.strokeStyle = color;
		ctx.lineWidth = 3;
		ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

		// Draw label
		ctx.fillStyle = color;
		const text = `${label} ${Math.round(confidence * 100)}%`;
		ctx.font = "16px Arial";
		const textWidth = ctx.measureText(text).width;
		ctx.fillRect(x1, y1 - 25, textWidth + 10, 25);

		ctx.fillStyle = "white";
		ctx.fillText(text, x1 + 5, y1 - 7);
	});
}

function backToEmployeeSection() {
	$("#image-detection-section").hide();
	$("#employee-section").show();
	clearImageUpload();
}

function switchToLiveScreening() {
	$("#image-detection-section").hide();
	clearImageUpload();
	startScreening();
}

function showImageUploadResult(passed, data) {
	const resultDiv = $("#image-screening-result");

	if (passed) {
		resultDiv.removeClass("fail").addClass("pass").show();
		resultDiv.html(
			'<h3><i class="ri-check-circle-line"></i> All required PPE detected!</h3>'
		);
	} else {
		const missing = data.missing_ppe
			.map((id) => requiredPPE.find((p) => p.id === id)?.name)
			.filter(Boolean)
			.join(", ");
		resultDiv.removeClass("pass").addClass("fail").show();
		resultDiv.html(
			`<h3><i class="ri-alert-line"></i> Missing: ${missing}</h3>`
		);
	}
}
