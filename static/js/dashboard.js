// Dashboard JavaScript
let sources = {};
let detectionEvents = [];
let eventSource = null;
let timeRange = 300; // Default 5 minutes

// Initialize dashboard
$(document).ready(function () {
	initializeEventStream();
	loadExistingSources();
	updateTimeRange();
	setInterval(updateTimeline, 1000); // Update timeline every second

	// Event handlers
	$("#source-type").change(function () {
		if ($(this).val() === "file") {
			$("#file-select-group").show();
			$("#stream-url-group").hide();
			loadVideoFiles();
		} else {
			$("#file-select-group").hide();
			$("#stream-url-group").show();
		}
	});

	$("#time-range").change(function () {
		timeRange = parseInt($(this).val());
		updateTimeline();
	});

	$("#detection-confidence").on("input", function () {
		$("#confidence-value").text($(this).val() + "%");
	});
});

// Initialize Server-Sent Events for real-time updates
function initializeEventStream() {
	eventSource = new EventSource("/events");

	eventSource.addEventListener("detection", function (event) {
		const data = JSON.parse(event.data);
		handleDetectionEvent(data);
	});

	eventSource.addEventListener("source_update", function (event) {
		const data = JSON.parse(event.data);
		updateSourceStatus(data);
	});

	eventSource.addEventListener("stats", function (event) {
		const data = JSON.parse(event.data);
		updateDashboardStats(data);
	});

	eventSource.onerror = function (error) {
		console.error("EventSource error:", error);
		setTimeout(initializeEventStream, 5000); // Retry after 5 seconds
	};
}

// Handle detection events
function handleDetectionEvent(data) {
	// Add to events array
	detectionEvents.push({
		source_id: data.source_id,
		timestamp: new Date(data.timestamp),
		violation_type: data.violation_type,
		confidence: data.confidence,
		event_id: data.event_id || "",
		frame_number: data.frame_number || 0,
	});

	// Keep only events within the time range
	const cutoffTime = new Date(Date.now() - timeRange * 1000);
	detectionEvents = detectionEvents.filter((e) => e.timestamp > cutoffTime);

	// Update timeline
	updateTimeline();

	// Show notification for high-confidence violations
	if (data.confidence > 0.8) {
		showNotification(
			`${data.violation_type} detected at ${
				sources[data.source_id]?.name || "Unknown"
			}`,
			"warning"
		);
	}
}

// Update source status
function updateSourceStatus(data) {
	if (sources[data.source_id]) {
		sources[data.source_id].status = data.status;
		sources[data.source_id].fps = data.fps;
		updateSourceCard(data.source_id);
	}
}

// Update dashboard statistics
function updateDashboardStats(stats) {
	$("#active-sources").text(stats.active_sources);
	$("#active-violations").text(stats.active_violations);
	$("#compliance-rate").text(Math.round(stats.compliance_rate) + "%");
	$("#last-detection").text(
		stats.last_detection ? formatTime(new Date(stats.last_detection)) : "--:--"
	);
}

// Load existing sources
function loadExistingSources() {
	$.ajax({
		url: "/api/sources",
		method: "GET",
		success: function (data) {
			sources = {};
			data.forEach((source) => {
				sources[source.id] = source;
				addSourceCard(source);
			});
			updateTimeline();
		},
	});
}

// Add a new source
function addSource() {
	const name = $("#source-name").val().trim();
	const type = $("#source-type").val();
	const path =
		type === "file" ? $("#video-file").val() : $("#stream-url").val();

	if (!path) {
		showNotification("Please select a source", "error");
		return;
	}

	$.ajax({
		url: "/api/sources",
		method: "POST",
		contentType: "application/json",
		data: JSON.stringify({
			name: name, // Can be empty, backend will auto-generate
			type: type,
			path: path,
		}),
		success: function (source) {
			sources[source.id] = source;
			addSourceCard(source);
			hideAddSourceModal();
			showNotification("Source added successfully", "success");
			$("#source-name").val("");
			$("#stream-url").val("");
		},
		error: function (xhr) {
			showNotification(
				xhr.responseJSON?.error || "Failed to add source",
				"error"
			);
		},
	});
}

// Remove a source
function removeSource(sourceId) {
	if (!confirm("Are you sure you want to remove this source?")) return;

	$.ajax({
		url: `/api/sources/${sourceId}`,
		method: "DELETE",
		success: function () {
			delete sources[sourceId];
			$(`#source-${sourceId}`).remove();
			updateTimeline();
			showNotification("Source removed successfully", "success");
		},
		error: function () {
			showNotification("Failed to remove source", "error");
		},
	});
}

// View source feed
function viewSource(sourceId) {
	window.open(`/camera/${sourceId}`, "_blank");
}

// Add source card to UI
function addSourceCard(source) {
	const card = $(`
        <div class="source-card" id="source-${source.id}">
            <div class="source-card-header">
                <h4>${source.name}</h4>
                <div class="source-status">
                    <span class="source-indicator ${
											source.status === "active" ? "" : "inactive"
										}"></span>
                    <span>${
											source.status === "active" ? "Active" : "Inactive"
										}</span>
                </div>
            </div>
            <div class="source-stats">
                <div class="stat-item">
                    <div class="stat-label">Violations</div>
                    <div class="stat-value violations-count">0</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">FPS</div>
                    <div class="stat-value fps-value">${source.fps || 0}</div>
                </div>
            </div>
            <div class="source-actions">
                <button class="btn-secondary" onclick="viewSource('${
									source.id
								}')">
                    <i class="ri-eye-line"></i> View
                </button>
                <button class="btn-secondary" onclick="removeSource('${
									source.id
								}')">
                    <i class="ri-delete-bin-line"></i> Remove
                </button>
            </div>
        </div>
    `);

	$("#sources-grid").append(card);
}

// Update source card
function updateSourceCard(sourceId) {
	const source = sources[sourceId];
	const card = $(`#source-${sourceId}`);

	card
		.find(".source-indicator")
		.toggleClass("inactive", source.status !== "active");
	card
		.find(".source-status span:last")
		.text(source.status === "active" ? "Active" : "Inactive");
	card.find(".fps-value").text(source.fps || 0);

	// Update violation count
	const violationCount = detectionEvents.filter(
		(e) => e.source_id === sourceId
	).length;
	card.find(".violations-count").text(violationCount);
}

// Update timeline visualization
function updateTimeline() {
	const container = $("#timeline-container");
	container.empty();

	// Group events by source
	const eventsBySource = {};
	detectionEvents.forEach((event) => {
		if (!eventsBySource[event.source_id]) {
			eventsBySource[event.source_id] = [];
		}
		eventsBySource[event.source_id].push(event);
	});

	// Create timeline for each source
	Object.keys(sources).forEach((sourceId) => {
		const source = sources[sourceId];
		const events = eventsBySource[sourceId] || [];

		const timeline = $(`
            <div class="timeline-source">
                <div class="timeline-source-header">
                    <span class="source-indicator ${
											source.status === "active" ? "" : "inactive"
										}"></span>
                    <span>${source.name}</span>
                </div>
                <div class="timeline-track" id="track-${sourceId}"></div>
            </div>
        `);

		container.append(timeline);

		// Add events to timeline
		const track = $(`#track-${sourceId}`);
		const trackWidth = track.width() || 800; // Default width
		const now = Date.now();

		events.forEach((event) => {
			const age = now - event.timestamp.getTime();
			const position =
				((timeRange * 1000 - age) / (timeRange * 1000)) * trackWidth;

			if (position > 0) {
				const eventEl = $(`
                    <div class="timeline-event ${event.violation_type
											.toLowerCase()
											.replace(" ", "-")}"
                         style="left: ${position}px;"
                         data-event-id="${event.event_id}"
                         data-source-id="${event.source_id}">
                    </div>
                `);

				// Add click handler for popup
				eventEl.on("click", function (e) {
					e.stopPropagation();
					showViolationPopup(event, $(this));
				});

				track.append(eventEl);
			}
		});

		// Update source card violation count
		updateSourceCard(sourceId);
	});

	// Add time axis
	addTimeAxis();
}

// Add time axis to timeline
function addTimeAxis() {
	const axis = $('<div class="timeline-axis"></div>');
	const markers = [0, 0.25, 0.5, 0.75, 1];

	markers.forEach((marker) => {
		const time = marker * timeRange;
		const label = formatDuration(time);
		const position = (1 - marker) * 100;

		axis.append(`
            <div class="time-marker" style="left: ${position}%">
                ${label}
            </div>
        `);
	});

	$("#timeline-container").append(axis);
}

// Format duration
function formatDuration(seconds) {
	if (seconds === 0) return "Now";
	if (seconds < 60) return `${seconds}s`;
	if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
	return `${Math.floor(seconds / 3600)}h`;
}

// Format time
function formatTime(date) {
	return date.toLocaleTimeString("en-US", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	});
}

// Load video files for dropdown
function loadVideoFiles() {
	$.ajax({
		url: "/video_list",
		method: "GET",
		success: function (response) {
			const data = JSON.parse(response);
			const select = $("#video-file");
			select.empty();

			if (data.videos.length === 0) {
				select.append('<option value="">No videos available</option>');
			} else {
				data.videos.forEach((video) => {
					select.append(`<option value="${video}">${video}</option>`);
				});
			}
		},
	});
}

// Export timeline data
function exportTimeline() {
	const data = {
		timeRange: timeRange,
		events: detectionEvents,
		sources: sources,
		exportTime: new Date().toISOString(),
	};

	const blob = new Blob([JSON.stringify(data, null, 2)], {
		type: "application/json",
	});
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = `timeline_export_${new Date().getTime()}.json`;
	a.click();
	URL.revokeObjectURL(url);

	showNotification("Timeline data exported", "success");
}

// Save settings
function saveSettings() {
	const email = $("#alert-email").val();
	const enableAlerts = $("#enable-alerts").is(":checked");
	const confidence = $("#detection-confidence").val() / 100;

	$.ajax({
		url: "/api/settings",
		method: "POST",
		contentType: "application/json",
		data: JSON.stringify({
			email_recipient: email,
			email_alert_enabled: enableAlerts,
			confidence_threshold: confidence,
		}),
		success: function () {
			hideSettings();
			showNotification("Settings saved successfully", "success");
		},
		error: function () {
			showNotification("Failed to save settings", "error");
		},
	});
}

// Modal functions
function showAddSourceModal() {
	$("#add-source-modal").fadeIn(200);
	$("#source-type").trigger("change");
}

function hideAddSourceModal() {
	$("#add-source-modal").fadeOut(200);
}

function showSettings() {
	$("#settings-modal").fadeIn(200);
}

function hideSettings() {
	$("#settings-modal").fadeOut(200);
}

// Fullscreen toggle
function toggleFullscreen() {
	if (!document.fullscreenElement) {
		document.documentElement.requestFullscreen();
	} else {
		document.exitFullscreen();
	}
}

// Update time range
function updateTimeRange() {
	setInterval(updateTimeline, 1000);
}

// Notification function
function showNotification(message, type = "info") {
	// Remove any existing notifications
	$(".notification").remove();

	const notification = $(`
        <div class="notification notification-${type}">
            <i class="ri-${getIconForType(type)} notification-icon"></i>
            <span>${message}</span>
        </div>
    `);

	$("body").append(notification);

	// Animate in
	setTimeout(() => notification.addClass("show"), 10);

	// Auto-hide after 4 seconds
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

// Show violation popup
function showViolationPopup(event, element) {
	// Remove any existing popup
	$(".violation-popup").remove();

	const source = sources[event.source_id];
	const popup = $(`
		<div class="violation-popup">
			<div class="popup-header">
				<h4>${event.violation_type}</h4>
				<button class="popup-close" onclick="hideViolationPopup()">
					<i class="ri-close-line"></i>
				</button>
			</div>
			<div class="popup-content">
				<div class="popup-detail">
					<span class="detail-label">Time:</span>
					<span class="detail-value">${formatTime(event.timestamp)}</span>
				</div>
				<div class="popup-detail">
					<span class="detail-label">Source:</span>
					<span class="detail-value">${source ? source.name : "Unknown"}</span>
				</div>
				<div class="popup-detail">
					<span class="detail-label">Confidence:</span>
					<span class="detail-value">${Math.round(event.confidence * 100)}%</span>
				</div>
				<div class="popup-detail">
					<span class="detail-label">Frame:</span>
					<span class="detail-value">#${event.frame_number}</span>
				</div>
			</div>
			<div class="popup-actions">
				<button class="btn-primary" onclick="viewSource('${event.source_id}')">
					<i class="ri-eye-line"></i> View Camera Feed
				</button>
			</div>
		</div>
	`);

	// Position popup near the clicked element
	const offset = element.offset();
	const windowHeight = $(window).height();
	const windowWidth = $(window).width();

	// Default position above the element
	let top = offset.top - 200;
	let left = offset.left - 100;

	// Adjust if popup would go off screen
	if (top < 50) {
		top = offset.top + 30; // Show below instead
	}
	if (left < 10) {
		left = 10;
	} else if (left + 220 > windowWidth) {
		left = windowWidth - 230;
	}

	popup.css({
		top: top + "px",
		left: left + "px",
	});

	$("body").append(popup);

	// Close popup when clicking outside
	setTimeout(() => {
		$(document).on("click.popup", function (e) {
			if (!$(e.target).closest(".violation-popup, .timeline-event").length) {
				hideViolationPopup();
			}
		});
	}, 10);
}

// Hide violation popup
function hideViolationPopup() {
	$(".violation-popup").remove();
	$(document).off("click.popup");
}
