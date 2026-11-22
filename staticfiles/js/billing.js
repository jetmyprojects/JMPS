
(function () {
    // Scope variables to avoid global pollution
    let currentPage = 1;
    const pageSize = 10;
    const tbody = document.getElementById('invoice-tbody');
    const cancelContainer = document.getElementById('cancel-btn-container');
    // Get URL from data attribute or fallback
    const configDiv = document.getElementById('billing-config');
    const cancelUrl = configDiv ? configDiv.getAttribute('data-cancel-url') : '#';


    // --- Define Helper Functions ---

    function renderTable(invoices) {
        if (!tbody) return;
        tbody.innerHTML = '';

        if (invoices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-5 text-muted">No transactions found in your history.</td></tr>';
            return;
        }

        invoices.forEach(invoice => {
            const date = new Date(invoice.created_at).toLocaleDateString('en-US', {
                year: 'numeric', month: 'short', day: 'numeric'
            });

            const amountVal = parseFloat(invoice.amount);
            const isTrial = amountVal === 0;

            const args = { style: 'currency', currency: invoice.currency };
            const amountDisplay = new Intl.NumberFormat('en-US', args).format(invoice.amount);

            // Custom Logic for Trial and Refunds
            let description = isTrial ? 'Trial Subscription Started' : 'Annual Premium Plan Subscription';
            if (invoice.status === 'refunded' || amountVal < 0) {
                description = 'Refund for Subscription';
            } else if (invoice.status === 'trial_start') {
                description = 'Trial Subscription Started';
            } else if (invoice.status === 'trial_end') {
                description = 'Trial Subscription Ended';
            }

            let statusBadge;
            if (isTrial && invoice.status !== 'trial_start' && invoice.status !== 'trial_end') {
                statusBadge = '<span class="badge bg-success">Trial Start</span>';
            } else if (invoice.status === 'refunded') {
                statusBadge = '<span class="badge bg-danger">Refunded</span>';
            } else if (invoice.status === 'trial_start') {
                statusBadge = '<span class="badge bg-success">Trial Start</span>';
            } else if (invoice.status === 'trial_end') {
                statusBadge = '<span class="badge bg-secondary">Trial End</span>';
            } else {
                statusBadge = invoice.status === 'paid'
                    ? '<span class="status-paid"><i class="fas fa-check-circle"></i> Paid</span>'
                    : `<span class="badge bg-light text-dark border">${invoice.status}</span>`;
            }

            let downloadLink;
            if (invoice.invoice_pdf) {
                downloadLink = `<a href="${invoice.invoice_pdf}" target="_blank" class="text-decoration-none" style="color: var(--brand-orange);"><i class="fas fa-file-pdf"></i> Download</a>`;
            } else if (isTrial) {
                if (invoice.invoice_pdf) {
                    downloadLink = `<a href="${invoice.invoice_pdf}" target="_blank" class="text-decoration-none" style="color: var(--brand-orange);"><i class="fas fa-file-pdf"></i> Download</a>`;
                } else {
                    downloadLink = '<span>(-)</span>';
                }
            } else {
                downloadLink = '<span class="text-muted small">Pending...</span>';
            }

            const expiryDisplay = invoice.expiry_date
                ? new Date(invoice.expiry_date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
                : '<span class="text-muted">-</span>';

            const row = `
                    <tr>
                        <td>${date}</td>
                        <td>${expiryDisplay}</td>
                        <td>${description}</td>
                        <td>${amountDisplay}</td>
                        <td>${statusBadge}</td>
                        <td>${downloadLink}</td>
                    </tr>
                `;
            tbody.insertAdjacentHTML('beforeend', row);
        });
    }

    function renderPagination(data) {
        const container = document.getElementById('paginationControls');
        if (!container) return;
        container.innerHTML = '';

        if (!data.count) return;

        const totalPages = Math.ceil(data.count / pageSize);
        if (totalPages <= 1) return;

        // Previous Button
        const prevBtn = document.createElement('button');
        prevBtn.className = `btn btn-sm ${data.previous ? 'btn-outline-secondary' : 'btn-outline-secondary disabled'}`;
        prevBtn.innerHTML = '<i class="fas fa-chevron-left me-1"></i>';
        prevBtn.onclick = () => {
            if (data.previous) fetchInvoices(currentPage - 1);
        };
        container.appendChild(prevBtn);

        // Numbered Buttons
        let startPage = Math.max(1, currentPage - 2);
        let endPage = Math.min(totalPages, currentPage + 2);

        if (currentPage <= 3) {
            endPage = Math.min(5, totalPages);
        }
        if (currentPage >= totalPages - 2) {
            startPage = Math.max(1, totalPages - 4);
        }

        if (startPage > 1) {
            addPageBtn(1, container);
            if (startPage > 2) addEllipsis(container);
        }

        for (let i = startPage; i <= endPage; i++) {
            addPageBtn(i, container);
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) addEllipsis(container);
            addPageBtn(totalPages, container);
        }

        // Next Button
        const nextBtn = document.createElement('button');
        nextBtn.className = `btn btn-sm ${data.next ? 'btn-outline-secondary' : 'btn-outline-secondary disabled'}`;
        nextBtn.innerHTML = '<i class="fas fa-chevron-right me-1"></i>';
        nextBtn.onclick = () => {
            if (data.next) fetchInvoices(currentPage + 1);
        };
        container.appendChild(nextBtn);
    }

    function addPageBtn(page, container) {
        const btn = document.createElement('button');
        const isActive = page === currentPage;
        btn.className = `btn btn-sm ${isActive ? 'btn-brand-orange text-white w-auto' : 'btn-outline-secondary'}`;
        btn.textContent = page;
        btn.onclick = () => fetchInvoices(page);
        container.appendChild(btn);
    }

    function addEllipsis(container) {
        const span = document.createElement('span');
        span.className = 'px-2 text-muted';
        span.textContent = '...';
        container.appendChild(span);
    }

    async function fetchInvoices(page = 1) {
        currentPage = page;
        const url = `/api/v1/billing/invoices/?page=${page}&page_size=${pageSize}`;

        try {
            const invoiceRes = await ApiClient.fetch(url);
            if (invoiceRes && invoiceRes.ok) {
                const data = await invoiceRes.json();
                const invoices = data.results || data;

                renderTable(invoices);
                renderPagination(data);
            } else {
                if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center py-5 text-danger">Failed to retrieve billing records.</td></tr>';
            }
        } catch (e) {
            console.error(e);
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center py-5 text-danger">An error occurred while loading your history.</td></tr>';
        }
    }

    async function fetchPlanInfo() {
        try {
            const planRes = await ApiClient.fetch('/api/v1/billing/plan/');
            if (planRes && planRes.ok) {
                const subData = await planRes.json();
                console.log("Plan Data:", subData); // DEBUG: Check is_trial flag

                if (!cancelContainer) return;

                // Prepare Logic
                const planId = subData.plan || (subData.plan_details && subData.plan_details.id);
                const isActive = subData.is_active;
                const isTrial = subData.is_trial;
                const isAutoRenew = subData.auto_renew;

                // State Determination
                // Renew: Disabled if Active AND (Trial OR AutoRenew)
                // Cancel: Disabled if NOT (Active AND (Trial OR AutoRenew))

                const isEncumbered = isActive && (isTrial || isAutoRenew); // User is locked in until cancel
                const canRenew = !isEncumbered; // Can only renew if NOT encumbered (i.e. cancelled or expired)
                const canCancel = isEncumbered; // Can only cancel if encumbered

                // 1. Build Renew Button
                let buttonsHtml = '';

                if (!planId) {
                    buttonsHtml = `
                        <a href="/#pricing" class="btn btn-brand-orange btn-sm">
                            <i class="fas fa-star"></i> Subscribe Now
                        </a>
                    `;
                } else {
                    // If disabled, add disabled attribute. 
                    // Note: If canRenew is false (user is active), we DISABLE it.
                    const renewDisabledAttr = canRenew ? '' : 'disabled';

                    buttonsHtml = `
                        <button onclick="handleSmartRenew(${!canRenew}, ${planId})" class="btn btn-brand-orange btn-sm" ${renewDisabledAttr}>
                            <i class="fas fa-sync-alt"></i> Renew Subscription
                        </button>
                    `;
                }

                // 2. Build Cancel Button
                if (planId) {
                    const cancelBtnClass = "btn btn-outline-danger btn-sm px-4 ms-2 cancel-btn";
                    const cancelIcon = '<i class="fas fa-times-circle"></i>';
                    const cancelText = 'Cancel Subscription';

                    if (canCancel) {
                        if (isTrial) {
                            // Trial -> Modal
                            buttonsHtml += `
                                <button onclick="openCancelModal()" class="${cancelBtnClass} cancel-btn">
                                    ${cancelIcon} ${cancelText}
                                </button>
                            `;
                        } else {
                            // Paid -> Link
                            buttonsHtml += `
                                <a href="/dashboard/billing/cancel/" class="${cancelBtnClass} cancel-btn">
                                    ${cancelIcon} ${cancelText}
                                </a>
                            `;
                        }
                    } else {
                        // Disabled Cancel Button
                        // "if already cancel then disable cancel button"
                        buttonsHtml += `
                            <button disabled class="${cancelBtnClass}">
                                ${cancelIcon} ${cancelText}
                            </button>
                        `;
                    }
                }

                // 3. Status Text (Removed as per request)
                let statusInfo = '';

                cancelContainer.innerHTML = buttonsHtml + statusInfo;
            }
        } catch (e) {
            console.error("Failed to fetch plan info", e);
        }
    }

    // New Window Function for Smart Renew
    window.handleSmartRenew = function (isBlocked, planId) {
        if (isBlocked) {
            // "if user is trail/subscribed then show toast message that cancle plan then renew"
            const msg = "Please cancel your current plan before renewing.";
            if (typeof showNotification === 'function') {
                showNotification(msg, 'error'); // error gives red icon, or warning? User said "toast message".
            } else {
                alert(msg);
            }
        } else {
            if (planId) {
                renewSubscription(planId);
            } else {
                // If no plan ID (should go to pricing?)
                window.location.href = '/#pricing';
            }
        }
    }

    // Expose these nicely? Or add to window below.
    window.openCancelModal = function () {
        console.log("openCancelModal called");
        const modalEl = document.getElementById('cancelModal');
        if (modalEl) {
            console.log("Modal element found:", modalEl);
            if (typeof bootstrap !== 'undefined') {
                const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
                modal.show();
            } else {
                console.error("Bootstrap is not defined inside openCancelModal.");
                alert("Error: Could not load modal library.");
            }
        } else {
            console.error("Cancel Modal element not found in DOM.");
        }
    }

    window.confirmCancelSubscription = async function () {
        const modalEl = document.getElementById('cancelModal');
        const modal = bootstrap.Modal.getInstance(modalEl);

        // Disable button
        const btn = modalEl.querySelector('.btn-danger');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Cancelling...';
        btn.disabled = true;

        try {
            // Using the existing configDiv url or hardcoded endpoint?
            // configDiv has data-cancel-url="{% url 'payment_cancel' %}" which maps to CancelSubscriptionView
            const configDiv = document.getElementById('billing-config');
            const cancelUrl = configDiv ? configDiv.getAttribute('data-cancel-url') : '/api/v1/billing/cancel/';

            const response = await ApiClient.fetch(cancelUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (response.ok) {
                // Redirect to history with a flag
                window.location.href = '/dashboard/billing/history/?cancelled=true';
            } else {
                const data = await response.json();
                alert('Failed to cancel: ' + (data.detail || data.error || 'Unknown error'));
            }
        } catch (e) {
            console.error(e);
            alert('An error occurred while cancelling.');
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
            // if (modal) modal.hide(); // No need if we redirect
        }
    }

    // --- Initialization ---
    const init = async () => {
        // Check for cancellation flag
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('cancelled') === 'true') {
            if (typeof showNotification === 'function') {
                showNotification('Subscription cancelled successfully.', 'success');
            } else {
                // Fallback if toast not available (though it should be in task_base)
                alert('Subscription cancelled successfully.');
            }
            // Clean URL
            const newUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
            window.history.replaceState({ path: newUrl }, '', newUrl);
        }

        if (typeof ApiClient === 'undefined') {
            console.error('ApiClient not loaded');
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center py-5 text-warning">API Client Loading...</td></tr>';
            // Retry once? Or just wait? 
            // Usually ApiClient is loaded in base template. 
            return;
        }

        await Promise.all([fetchPlanInfo(), fetchInvoices()]);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

// --- Global Functions (Window) ---

(function () {
    // Renewal Logic State (Scoped to this execution)
    let selectedPlanId = null;
    let renewModalObj = null;

    // Verify Logic
    window.verifyDiscount = async function () {
        const codeInput = document.getElementById('renewDiscountCode');
        const alertBox = document.getElementById('renewAlert');
        const code = codeInput.value.trim();
        const verifyBtn = document.getElementById('btnVerifyCode');

        if (!code) {
            alertBox.className = 'alert alert-danger mt-2 p-2 small';
            alertBox.innerText = 'Please enter a code to verify.';
            alertBox.classList.remove('d-none');
            return;
        }

        // Reset UI
        alertBox.classList.add('d-none');
        const originalHTML = verifyBtn.innerHTML;
        verifyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        verifyBtn.disabled = true;
        codeInput.disabled = true;

        try {
            const response = await ApiClient.fetch('/api/v1/payments/validate-discount/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            });

            const data = await response.json();

            if (response.ok && data.valid) {
                alertBox.className = 'alert alert-success mt-2 p-2 small';
                alertBox.innerHTML = `<i class="fas fa-check-circle"></i> Valid! <strong>${data.discount_percent}% OFF</strong> applied.`;
                alertBox.classList.remove('d-none');
            } else {
                alertBox.className = 'alert alert-danger mt-2 p-2 small';
                alertBox.innerText = data.error || 'Invalid code.';
                alertBox.classList.remove('d-none');
            }
        } catch (e) {
            console.error('Verify error:', e);
            alertBox.className = 'alert alert-danger mt-2 p-2 small';
            alertBox.innerText = 'Could not verify code. Please try again.';
            alertBox.classList.remove('d-none');
        } finally {
            verifyBtn.innerHTML = originalHTML;
            verifyBtn.disabled = false;
            codeInput.disabled = false;
        }
    }

    // Open Modal
    window.renewSubscription = function (planId) {
        if (!planId) return;
        selectedPlanId = planId;

        // cleanup
        document.getElementById('renewDiscountCode').value = '';
        const alertBox = document.getElementById('renewAlert');
        if (alertBox) {
            alertBox.classList.add('d-none');
            alertBox.className = 'alert alert-danger mt-2 d-none p-2 small';
            alertBox.innerText = '';
        }

        const modalEl = document.getElementById('renewModal');
        if (modalEl) {
            // Re-create modal instance or use existing if global var persists across IIFEs (but here local var resets)
            // Bootstrap Modal.getOrCreateInstance is safer if multiple inits happen
            renewModalObj = bootstrap.Modal.getOrCreateInstance(modalEl);
            renewModalObj.show();
        }
    }

    // Process Renewal (Skip or Apply)
    window.processRenewal = async function (skip) {
        if (!selectedPlanId) return;

        const codeInput = document.getElementById('renewDiscountCode');
        const alertBox = document.getElementById('renewAlert');
        const code = skip ? null : codeInput.value.trim();

        const applyBtn = document.querySelector('#renewModal .btn-brand-orange');
        const skipBtn = document.querySelector('#renewModal .btn-outline-secondary');

        // Reset UI
        alertBox.classList.add('d-none');

        // Basic validation
        if (!skip && !code) {
            alertBox.innerText = 'Please enter a code or click Skip.';
            alertBox.classList.remove('d-none');
            return;
        }

        // Loading State
        const originalApplyText = applyBtn.innerHTML;
        const originalSkipText = skipBtn.innerHTML;

        applyBtn.disabled = true;
        skipBtn.disabled = true;

        if (!skip) applyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
        else skipBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

        if (!skip) applyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';
        else skipBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

        try {
            // Step 1: Validate Code first if provided
            if (!skip && code) {
                const validateRes = await ApiClient.fetch('/api/v1/payments/validate-discount/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code })
                });
                const validateData = await validateRes.json();

                if (!validateRes.ok || !validateData.valid) {
                    throw new Error(validateData.error || 'Invalid discount code.');
                }
            }

            // Step 2: Create Session
            const response = await ApiClient.fetch('/api/v1/payments/create-session/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plan_id: selectedPlanId,
                    discount_code: code
                })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.url) {
                    window.location.href = data.url;
                } else if (data.success || data.trial_activated) {
                    // Success (100% off / Trial) - No redirect needed
                    window.location.href = '/dashboard/billing/history/';
                } else {
                    throw new Error('No checkout URL returned');
                }
            } else {
                const err = await response.json();
                const errMsg = err.error || err.detail || 'Failed to initiate renewal.';

                // Show error in toast if "already used"
                if (errMsg.toLowerCase().includes('already used')) {
                    if (typeof showNotification === 'function') {
                        showNotification(errMsg, 'error');
                    }
                    // Close modal? Or keep open to let them try another code?
                    // Keep open but reset UI maybe?
                }

                // Always show in modal too (red box)
                alertBox.className = 'alert alert-danger mt-2 p-2 small';
                alertBox.innerText = errMsg;
                alertBox.classList.remove('d-none');

                // Reset Buttons
                applyBtn.disabled = false;
                skipBtn.disabled = false;
                applyBtn.innerHTML = originalApplyText;
                skipBtn.innerHTML = originalSkipText;
            }
        } catch (e) {
            console.error('Renew error:', e);
            alertBox.className = 'alert alert-danger mt-2 p-2 small';
            // DEBUG: Show actual error to user to identify issue
            alertBox.innerText = 'Error: ' + (e.message || e);
            alertBox.classList.remove('d-none');

            applyBtn.disabled = false;
            skipBtn.disabled = false;
            applyBtn.innerHTML = originalApplyText;
            skipBtn.innerHTML = originalSkipText;
        }
    }
})();

