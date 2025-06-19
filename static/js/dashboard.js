// Dashboard JavaScript
let sources = {};
let detectionEvents = [];
let eventSource = null;
let timeRange = 300; // Default 5 minutes
let activeViolationCategories = new Set(); // Track unique violation categories

// Initialize dashboard
$(document).ready(function () {
	// Initialize theme
	initializeTheme();

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

	// Theme change handlers
	$('input[name="theme"]').change(function () {
		const theme = $(this).val();
		applyTheme(theme);
		localStorage.setItem("theme", theme);
	});
});

// Theme Management Functions
function initializeTheme() {
	const savedTheme = localStorage.getItem("theme") || "dark";

	// Check the appropriate radio button
	$(`#theme-${savedTheme}`).prop("checked", true);

	// Apply the theme
	applyTheme(savedTheme);
}

function applyTheme(theme) {
	if (theme === "auto") {
		// Check system preference
		const prefersDark = window.matchMedia(
			"(prefers-color-scheme: dark)"
		).matches;
		theme = prefersDark ? "dark" : "light";
	}

	// Apply theme to body
	document.documentElement.setAttribute("data-theme", theme);
}

// Listen for system theme changes when auto is selected
window
	.matchMedia("(prefers-color-scheme: dark)")
	.addEventListener("change", (e) => {
		const currentTheme = localStorage.getItem("theme");
		if (currentTheme === "auto") {
			applyTheme("auto");
		}
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

	// Update violation tracking
	updateViolationTracking();

	// Update timeline
	updateTimeline();

	// Update violation banners instead of spamming notifications
	updateViolationBanners();
}

// Update violation tracking for unique categories
function updateViolationTracking() {
	// Get current active violations by source
	const violationsBySource = {};

	detectionEvents.forEach((event) => {
		if (!violationsBySource[event.source_id]) {
			violationsBySource[event.source_id] = new Set();
		}
		violationsBySource[event.source_id].add(event.violation_type);
	});

	// Update active violation categories globally
	activeViolationCategories.clear();
	Object.values(violationsBySource).forEach((violations) => {
		violations.forEach((v) => activeViolationCategories.add(v));
	});

	// Update UI
	$("#active-violations").text(activeViolationCategories.size);
}

// Update violation banners
function updateViolationBanners() {
	// Group violations by source
	const violationsBySource = {};

	detectionEvents.forEach((event) => {
		if (!violationsBySource[event.source_id]) {
			violationsBySource[event.source_id] = [];
		}
		// Add violation info
		const existing = violationsBySource[event.source_id].find(
			(v) => v.type === event.violation_type
		);
		if (!existing) {
			violationsBySource[event.source_id].push({
				type: event.violation_type,
				lastSeen: event.timestamp,
				count: 1,
			});
		} else {
			existing.count++;
			existing.lastSeen = event.timestamp;
		}
	});

	// Update banners for each source
	Object.keys(sources).forEach((sourceId) => {
		const violations = violationsBySource[sourceId] || [];
		if (window.ViolationBanners) {
			window.ViolationBanners.updateViolations(sourceId, violations);
		}
	});
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
	// Use our tracked unique categories instead of the server's count
	$("#active-violations").text(activeViolationCategories.size);
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
			// Clear any violation banners for this source
			if (window.ViolationBanners) {
				window.ViolationBanners.updateViolations(sourceId, []);
			}
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
        <div class="source-card animate-on-load" id="source-${source.id}">
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
                <button class="btn-secondary button-press" onclick="viewSource('${
									source.id
								}')">
                    <i class="ri-eye-line"></i> View
                </button>
                <button class="btn-secondary button-press" onclick="removeSource('${
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

	// Update violation count - count unique violation types for this source
	const uniqueViolations = new Set();
	detectionEvents
		.filter((e) => e.source_id === sourceId)
		.forEach((e) => uniqueViolations.add(e.violation_type));

	card.find(".violations-count").text(uniqueViolations.size);
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
                    <span class="timeline-source-name">${source.name}</span>
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
	const numMarkers = 4; // Show 5 markers total (0 to 4)

	for (let i = 0; i <= numMarkers; i++) {
		const fraction = i / numMarkers;
		const time = fraction * timeRange;
		const label = formatDuration(time);
		const position = fraction * 100; // Fix: position from left to right

		axis.append(`
            <div class="time-marker" style="left: ${position}%">
                <span class="marker-label">${label}</span>
            </div>
        `);
	}

	$("#timeline-container").append(axis);
}

// Format duration
function formatDuration(seconds) {
	if (seconds >= timeRange) return "Now";
	if (seconds === 0) return `-${timeRange}s`;
	const remaining = timeRange - seconds;
	if (remaining < 60) return `-${Math.round(remaining)}s`;
	if (remaining < 3600) return `-${Math.floor(remaining / 60)}m`;
	return `-${Math.floor(remaining / 3600)}h`;
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
		uniqueViolationCategories: Array.from(activeViolationCategories),
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
	const theme = $('input[name="theme"]:checked').val();

	// Save theme preference
	localStorage.setItem("theme", theme);
	applyTheme(theme);

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

function updateTimeRange() {
	// Remove old events outside the time range
	const cutoffTime = new Date(Date.now() - timeRange * 1000);
	detectionEvents = detectionEvents.filter((e) => e.timestamp > cutoffTime);
	updateViolationTracking();
	updateViolationBanners();
}

function showNotification(message, type = "info") {
	// Use the Apple UI notification system if available
	if (window.AppleUI) {
		window.AppleUI.showNotification({
			message: message,
			type: type,
		});
	} else {
		// Fallback to simple notification
		console.log(`[${type.toUpperCase()}] ${message}`);
	}
}

function showViolationPopup(event, element) {
	// Remove any existing popup
	$(".violation-popup").remove();

	const popup = $(
		`<div class="violation-popup">
			<div class="popup-header">
				<h4>Violation Details</h4>
				<button class="popup-close"><i class="ri-close-line"></i></button>
			</div>
			<div class="popup-content">
				<div class="popup-detail"><span class="detail-label">Type:</span><span class="detail-value">${
					event.violation_type
				}</span></div>
				<div class="popup-detail"><span class="detail-label">Source:</span><span class="detail-value">${
					sources[event.source_id]?.name || "Unknown"
				}</span></div>
				<div class="popup-detail"><span class="detail-label">Time:</span><span class="detail-value">${formatTime(
					event.timestamp
				)}</span></div>
				<div class="popup-detail"><span class="detail-label">Confidence:</span><span class="detail-value">${Math.round(
					event.confidence * 100
				)}%</span></div>
			</div>
			<div class="popup-actions"><button class="btn-primary button-press" onclick="viewSource('${
				event.source_id
			}')"><i class="ri-eye-line"></i> View Source</button></div>
		</div>`
	);

	$("body").append(popup);

	// Calculate position after element is in DOM to get dimensions
	const popupWidth = popup.outerWidth();
	const popupHeight = popup.outerHeight();

	const rect = element[0].getBoundingClientRect();
	let left = rect.left + rect.width / 2 - popupWidth / 2;
	let top = rect.top - popupHeight - 12; // above marker

	// Clamp within viewport
	left = Math.max(10, Math.min(left, window.innerWidth - popupWidth - 10));
	if (top < 10) {
		// place below if not enough space above
		top = rect.bottom + 12;
		if (top + popupHeight > window.innerHeight - 10) {
			// fallback to center vertically
			top = (window.innerHeight - popupHeight) / 2;
		}
	}

	popup.css({ left: `${left}px`, top: `${top}px` });

	setTimeout(() => popup.addClass("show"), 10);

	// Close handlers
	popup.find(".popup-close").on("click", hideViolationPopup);
	$(document).on("click.popup", function (e) {
		if (!$(e.target).closest(".violation-popup, .timeline-event").length) {
			hideViolationPopup();
		}
	});
}

function hideViolationPopup() {
	$(".violation-popup").removeClass("show");
	setTimeout(() => $(".violation-popup").remove(), 300);
	$(document).off("click.popup");
}
