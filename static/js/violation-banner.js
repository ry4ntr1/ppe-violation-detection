/**
 * Smart Violation Banner System
 * Shows individual banners for each violation type
 */

class ViolationBannerSystem {
	constructor() {
		this.activeBanners = new Map(); // key -> { violation, element, sourceId, sourceName }
		this.dismissedBanners = new Set(); // Set of sourceId-violationType combinations
		this.initContainer();
	}

	initContainer() {
		if (!$("#violation-banner-container").length) {
			$("body").append(`
                <div id="violation-banner-container" class="violation-banner-container">
                </div>
            `);
		}
	}

	/**
	 * Update violation status for a source
	 */
	updateViolations(sourceId, violations) {
		const sourceName = sources[sourceId]?.name || "Unknown Source";

		// Get current active violations for this source
		const currentBannerKeys = [];
		this.activeBanners.forEach((banner, key) => {
			if (banner.sourceId === sourceId) {
				currentBannerKeys.push(key);
			}
		});

		// Get new violation keys
		const newViolationKeys = violations.map((v) => `${sourceId}-${v.type}`);

		// Remove banners for violations that are no longer active
		currentBannerKeys.forEach((key) => {
			if (!newViolationKeys.includes(key)) {
				this.removeBanner(key);
			}
		});

		// Add or update banners for active violations
		violations.forEach((violation) => {
			const key = `${sourceId}-${violation.type}`;

			if (!this.dismissedBanners.has(key)) {
				if (!this.activeBanners.has(key)) {
					// Create new banner
					this.createBanner(key, violation, sourceId, sourceName);
				} else {
					// Update existing banner if needed
					this.updateBanner(key, violation);
				}
			}
		});
	}

	/**
	 * Create a new violation banner
	 */
	createBanner(key, violation, sourceId, sourceName) {
		const banner = $(`
            <div class="violation-banner" data-key="${key}">
                <div class="banner-content">
                    <div class="banner-icon">
                        <i class="ri-alert-fill"></i>
                    </div>
                    <div class="banner-text">
                        <div class="banner-title">${sourceName}</div>
                        <div class="banner-message">${violation.type} detected (${violation.count}x)</div>
                    </div>
                    <div class="banner-actions">
                        <button class="banner-action view" title="View Source">
                            <i class="ri-eye-line"></i>
                        </button>
                        <button class="banner-action dismiss" title="Dismiss">
                            <i class="ri-close-line"></i>
                        </button>
                    </div>
                </div>
                <div class="banner-progress"></div>
            </div>
        `);

		// Add violation type class for styling
		const violationClass = violation.type.toLowerCase().replace(/\s+/g, "-");
		banner.addClass(`violation-${violationClass}`);

		// Add swipe to dismiss on mobile
		this.addSwipeGesture(banner);

		// Handle view button - navigate to camera view in same tab
		banner.find(".view").on("click", () => {
			// Navigate to camera view page in same tab
			window.location.href = `/camera/${sourceId}`;
		});

		// Handle dismiss button
		banner.find(".dismiss").on("click", () => {
			this.dismissBanner(key);
		});

		// Add to container with animation
		$("#violation-banner-container").append(banner);
		setTimeout(() => banner.addClass("show"), 10);

		// Store reference
		this.activeBanners.set(key, {
			violation: violation,
			element: banner,
			sourceId: sourceId,
			sourceName: sourceName,
		});
	}

	/**
	 * Update existing banner
	 */
	updateBanner(key, violation) {
		const banner = this.activeBanners.get(key);
		if (!banner) return;

		// Update count
		banner.element
			.find(".banner-message")
			.text(`${violation.type} detected (${violation.count}x)`);

		// Pulse animation to show update
		banner.element.addClass("pulse");
		setTimeout(() => banner.element.removeClass("pulse"), 600);
	}

	/**
	 * Remove a banner
	 */
	removeBanner(key) {
		const banner = this.activeBanners.get(key);
		if (!banner) return;

		banner.element.removeClass("show");
		setTimeout(() => {
			banner.element.remove();
			this.activeBanners.delete(key);
		}, 300);
	}

	/**
	 * Dismiss a banner and remember the dismissal
	 */
	dismissBanner(key) {
		// Remember dismissal
		this.dismissedBanners.add(key);

		// Remove the banner
		this.removeBanner(key);

		// Clear dismissal after 5 minutes
		setTimeout(() => {
			this.dismissedBanners.delete(key);
		}, 5 * 60 * 1000);
	}

	/**
	 * Add swipe gesture for mobile
	 */
	addSwipeGesture(banner) {
		let startX = 0;
		let currentX = 0;
		let isDragging = false;

		const handleStart = (e) => {
			isDragging = true;
			startX = e.type.includes("mouse") ? e.clientX : e.touches[0].clientX;
			banner.css("transition", "none");
		};

		const handleMove = (e) => {
			if (!isDragging) return;

			currentX = e.type.includes("mouse") ? e.clientX : e.touches[0].clientX;
			const deltaX = currentX - startX;

			// Only allow swiping right
			if (deltaX > 0) {
				banner.css("transform", `translateX(${deltaX}px)`);
				banner.css("opacity", 1 - deltaX / 300);
			}
		};

		const handleEnd = () => {
			if (!isDragging) return;
			isDragging = false;

			banner.css("transition", "");
			const deltaX = currentX - startX;

			if (deltaX > 100) {
				// Dismiss if swiped far enough
				const key = banner.data("key");
				this.dismissBanner(key);
			} else {
				// Snap back
				banner.css("transform", "");
				banner.css("opacity", "");
			}
		};

		// Mouse events
		banner.on("mousedown", handleStart);
		$(document).on("mousemove", handleMove);
		$(document).on("mouseup", handleEnd);

		// Touch events
		banner.on("touchstart", handleStart);
		banner.on("touchmove", handleMove);
		banner.on("touchend", handleEnd);
	}

	/**
	 * Clear all banners
	 */
	clearAll() {
		this.activeBanners.forEach((_, key) => {
			this.removeBanner(key);
		});
		this.dismissedBanners.clear();
	}
}

// Initialize the banner system
const violationBanners = new ViolationBannerSystem();

// Export for use in other files
window.ViolationBanners = violationBanners;
