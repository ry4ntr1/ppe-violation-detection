/**
 * Apple-inspired UI Components for PPE Detection System
 * Emphasizes smooth animations, intuitive interactions, and accessibility
 */

class AppleUIComponents {
	/**
	 * Smart Loading Button with progress indication
	 */
	static createLoadingButton(text, onClick) {
		const button = $(`
            <button class="btn-primary button-press hover-lift">
                <span class="button-content">
                    <i class="button-icon ri-shield-check-line"></i>
                    <span class="button-text">${text}</span>
                </span>
                <span class="button-loader" style="display: none;">
                    <svg class="spinner" width="20" height="20" viewBox="0 0 20 20">
                        <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="50" stroke-dashoffset="10">
                            <animateTransform attributeName="transform" type="rotate" from="0 10 10" to="360 10 10" dur="1s" repeatCount="indefinite"/>
                        </circle>
                    </svg>
                </span>
            </button>
        `);

		button.on("click", async function (e) {
			e.preventDefault();
			const $btn = $(this);

			if ($btn.hasClass("loading")) return;

			$btn.addClass("loading");
			$btn.find(".button-content").fadeOut(150, function () {
				$btn.find(".button-loader").fadeIn(150);
			});

			try {
				await onClick();
			} finally {
				$btn.find(".button-loader").fadeOut(150, function () {
					$btn.find(".button-content").fadeIn(150);
					$btn.removeClass("loading");
				});
			}
		});

		return button;
	}

	/**
	 * Animated Counter for statistics
	 */
	static animateCounter(element, endValue, duration = 1000) {
		const $el = $(element);
		const startValue = parseInt($el.text()) || 0;
		const startTime = performance.now();

		const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4);

		const animate = (currentTime) => {
			const elapsed = currentTime - startTime;
			const progress = Math.min(elapsed / duration, 1);
			const easedProgress = easeOutQuart(progress);
			const currentValue = Math.floor(
				startValue + (endValue - startValue) * easedProgress
			);

			$el.text(currentValue);

			if (progress < 1) {
				requestAnimationFrame(animate);
			}
		};

		requestAnimationFrame(animate);
	}

	/**
	 * Smart Notification System
	 */
	static showNotification(options = {}) {
		const defaults = {
			title: "",
			message: "",
			type: "info",
			duration: 4000,
			actions: [],
			position: "top-right",
		};

		const settings = { ...defaults, ...options };
		const id = `notification-${Date.now()}`;

		const notification = $(`
            <div id="${id}" class="smart-notification ${
			settings.type
		}" data-position="${settings.position}">
                <div class="notification-icon">
                    <i class="ri-${this.getIconForType(settings.type)}"></i>
                </div>
                <div class="notification-content">
                    ${
											settings.title
												? `<h4 class="notification-title">${settings.title}</h4>`
												: ""
										}
                    <p class="notification-message">${settings.message}</p>
                    ${
											settings.actions.length
												? `
                        <div class="notification-actions">
                            ${settings.actions
															.map(
																(action) => `
                                <button class="notification-action" data-action="${action.id}">
                                    ${action.label}
                                </button>
                            `
															)
															.join("")}
                        </div>
                    `
												: ""
										}
                </div>
                <button class="notification-close">
                    <i class="ri-close-line"></i>
                </button>
            </div>
        `);

		// Add to body
		$("body").append(notification);

		// Animate in
		setTimeout(() => notification.addClass("show"), 10);

		// Handle actions
		notification.find(".notification-action").on("click", function () {
			const actionId = $(this).data("action");
			const action = settings.actions.find((a) => a.id === actionId);
			if (action && action.handler) {
				action.handler();
			}
			closeNotification();
		});

		// Handle close
		const closeNotification = () => {
			notification.removeClass("show");
			setTimeout(() => notification.remove(), 300);
		};

		notification.find(".notification-close").on("click", closeNotification);

		// Auto-dismiss
		if (settings.duration > 0) {
			setTimeout(closeNotification, settings.duration);
		}

		return notification;
	}

	static getIconForType(type) {
		const icons = {
			success: "check-circle-line",
			error: "error-warning-line",
			warning: "alert-line",
			info: "information-line",
		};
		return icons[type] || icons.info;
	}

	/**
	 * Skeleton Loader for async content
	 */
	static createSkeletonLoader(type = "card") {
		const templates = {
			card: `
                <div class="skeleton-card animate-pulse">
                    <div class="skeleton-header">
                        <div class="skeleton-loader" style="width: 60%; height: 24px;"></div>
                        <div class="skeleton-loader" style="width: 80px; height: 24px; border-radius: 12px;"></div>
                    </div>
                    <div class="skeleton-body">
                        <div class="skeleton-loader" style="width: 100%; height: 60px; margin-bottom: 12px;"></div>
                        <div class="skeleton-loader" style="width: 80%; height: 16px; margin-bottom: 8px;"></div>
                        <div class="skeleton-loader" style="width: 60%; height: 16px;"></div>
                    </div>
                </div>
            `,
			timeline: `
                <div class="skeleton-timeline animate-pulse">
                    <div class="skeleton-loader" style="width: 120px; height: 20px; margin-bottom: 12px;"></div>
                    <div class="skeleton-loader" style="width: 100%; height: 40px; border-radius: 8px;"></div>
                </div>
            `,
			list: `
                <div class="skeleton-list animate-pulse">
                    ${[1, 2, 3]
											.map(
												() => `
                        <div class="skeleton-list-item">
                            <div class="skeleton-loader" style="width: 40px; height: 40px; border-radius: 8px;"></div>
                            <div class="skeleton-list-content">
                                <div class="skeleton-loader" style="width: 70%; height: 18px; margin-bottom: 8px;"></div>
                                <div class="skeleton-loader" style="width: 50%; height: 14px;"></div>
                            </div>
                        </div>
                    `
											)
											.join("")}
                </div>
            `,
		};

		return $(templates[type] || templates.card);
	}

	/**
	 * Smooth Modal System
	 */
	static showModal(options = {}) {
		const defaults = {
			title: "",
			content: "",
			size: "medium",
			actions: [],
			closeOnBackdrop: true,
		};

		const settings = { ...defaults, ...options };
		const id = `modal-${Date.now()}`;

		const modal = $(`
            <div id="${id}" class="apple-modal ${settings.size}">
                <div class="modal-backdrop"></div>
                <div class="modal-dialog">
                    <div class="modal-content">
                        ${
													settings.title
														? `
                            <div class="modal-header">
                                <h3 class="modal-title">${settings.title}</h3>
                                <button class="modal-close">
                                    <i class="ri-close-line"></i>
                                </button>
                            </div>
                        `
														: ""
												}
                        <div class="modal-body">
                            ${settings.content}
                        </div>
                        ${
													settings.actions.length
														? `
                            <div class="modal-footer">
                                ${settings.actions
																	.map(
																		(action) => `
                                    <button class="btn-${
																			action.type || "secondary"
																		} ${action.class || ""}" data-action="${
																			action.id
																		}">
                                        ${
																					action.icon
																						? `<i class="${action.icon}"></i>`
																						: ""
																				}
                                        ${action.label}
                                    </button>
                                `
																	)
																	.join("")}
                            </div>
                        `
														: ""
												}
                    </div>
                </div>
            </div>
        `);

		// Add to body
		$("body").append(modal);

		// Animate in
		setTimeout(() => modal.addClass("show"), 10);

		// Handle close
		const closeModal = () => {
			modal.removeClass("show");
			setTimeout(() => modal.remove(), 300);
		};

		modal.find(".modal-close").on("click", closeModal);

		if (settings.closeOnBackdrop) {
			modal.find(".modal-backdrop").on("click", closeModal);
		}

		// Handle actions
		modal.find("[data-action]").on("click", function () {
			const actionId = $(this).data("action");
			const action = settings.actions.find((a) => a.id === actionId);
			if (action && action.handler) {
				const shouldClose = action.handler(modal) !== false;
				if (shouldClose) {
					closeModal();
				}
			}
		});

		return modal;
	}

	/**
	 * Touch-friendly Slider Component
	 */
	static createSlider(options = {}) {
		const defaults = {
			min: 0,
			max: 100,
			value: 50,
			step: 1,
			onChange: () => {},
			format: (val) => val,
		};

		const settings = { ...defaults, ...options };
		const id = `slider-${Date.now()}`;

		const slider = $(`
            <div id="${id}" class="apple-slider">
                <div class="slider-track">
                    <div class="slider-fill" style="width: ${
											settings.value
										}%"></div>
                    <div class="slider-thumb" style="left: ${settings.value}%">
                        <div class="slider-value">${settings.format(
													settings.value
												)}</div>
                    </div>
                </div>
            </div>
        `);

		let isDragging = false;
		const track = slider.find(".slider-track");
		const thumb = slider.find(".slider-thumb");
		const fill = slider.find(".slider-fill");
		const valueDisplay = slider.find(".slider-value");

		const updateValue = (pageX) => {
			const rect = track[0].getBoundingClientRect();
			const percent = Math.max(
				0,
				Math.min(100, ((pageX - rect.left) / rect.width) * 100)
			);
			const value = Math.round(
				(percent / 100) * (settings.max - settings.min) + settings.min
			);

			thumb.css("left", percent + "%");
			fill.css("width", percent + "%");
			valueDisplay.text(settings.format(value));

			settings.onChange(value);
		};

		// Mouse events
		thumb.on("mousedown", (e) => {
			isDragging = true;
			slider.addClass("dragging");
			e.preventDefault();
		});

		$(document).on("mousemove", (e) => {
			if (isDragging) {
				updateValue(e.pageX);
			}
		});

		$(document).on("mouseup", () => {
			if (isDragging) {
				isDragging = false;
				slider.removeClass("dragging");
			}
		});

		// Touch events
		thumb.on("touchstart", (e) => {
			isDragging = true;
			slider.addClass("dragging");
			e.preventDefault();
		});

		$(document).on("touchmove", (e) => {
			if (isDragging) {
				updateValue(e.touches[0].pageX);
			}
		});

		$(document).on("touchend", () => {
			if (isDragging) {
				isDragging = false;
				slider.removeClass("dragging");
			}
		});

		// Click on track
		track.on("click", (e) => {
			if (!isDragging) {
				updateValue(e.pageX);
			}
		});

		return slider;
	}

	/**
	 * Contextual Menu System
	 */
	static showContextMenu(event, items) {
		// Remove any existing context menus
		$(".apple-context-menu").remove();

		const menu = $(`
            <div class="apple-context-menu">
                ${items
									.map((item) => {
										if (item.divider) {
											return '<div class="context-menu-divider"></div>';
										}
										return `
                        <div class="context-menu-item ${
													item.disabled ? "disabled" : ""
												}" data-action="${item.id}">
                            ${item.icon ? `<i class="${item.icon}"></i>` : ""}
                            <span>${item.label}</span>
                            ${
															item.shortcut
																? `<span class="shortcut">${item.shortcut}</span>`
																: ""
														}
                        </div>
                    `;
									})
									.join("")}
            </div>
        `);

		// Position menu
		$("body").append(menu);

		// Calculate position to keep menu on screen
		const menuWidth = menu.outerWidth();
		const menuHeight = menu.outerHeight();
		const windowWidth = $(window).width();
		const windowHeight = $(window).height();

		let left = event.pageX;
		let top = event.pageY;

		if (left + menuWidth > windowWidth) {
			left = windowWidth - menuWidth - 10;
		}

		if (top + menuHeight > windowHeight) {
			top = windowHeight - menuHeight - 10;
		}

		menu.css({ left, top });

		// Animate in
		setTimeout(() => menu.addClass("show"), 10);

		// Handle item clicks
		menu.find(".context-menu-item:not(.disabled)").on("click", function () {
			const actionId = $(this).data("action");
			const item = items.find((i) => i.id === actionId);
			if (item && item.handler) {
				item.handler();
			}
			menu.removeClass("show");
			setTimeout(() => menu.remove(), 200);
		});

		// Close on outside click
		$(document).one("click", () => {
			menu.removeClass("show");
			setTimeout(() => menu.remove(), 200);
		});

		// Prevent event bubbling
		event.preventDefault();
		event.stopPropagation();
	}
}

// Export for use in other files
window.AppleUI = AppleUIComponents;
