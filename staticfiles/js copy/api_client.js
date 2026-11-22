const ApiClient = {
    /**
     * Perform an authenticated fetch request.
     * The browser automatically sends HttpOnly cookies (access_token).
     * Automatically handles 401 Unauthorized by calling refresh endpoint.
     * Uses a mutex (promise) to prevent multiple simultaneous refresh requests.
     * 
     * @param {string} url - The URL to fetch
     * @param {object} options - Fetch options
     * @returns {Promise<Response>} - The fetch response
     */
    fetch: async (url, options = {}) => {
        // Ensure headers exist
        options.headers = options.headers || {};
        options.credentials = 'include'; // Ensure cookies are sent (for CORS if needed, but same-origin is default)

        // No need to inject Authorization header anymore!

        // Initial Request
        let response = await fetch(url, options);

        // If 401 Unauthorized, try to refresh token
        if (response.status === 401) {
            console.log('Access token expired/missing. Checking for refresh...');

            // If no refresh is currently happening, start one
            if (!ApiClient.refreshPromise) {
                console.log('Initiating refresh...');
                ApiClient.refreshPromise = (async () => {
                    // Call refresh endpoint. The browser sends the refresh_token cookie.
                    const refreshResponse = await fetch('/api/v1/accounts/auth/token/refresh/', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({}) // Empty body, we rely on cookie
                    });

                    if (!refreshResponse.ok) {
                        throw new Error('Refresh token invalid or expired');
                    }

                    // The response sets new cookies. We don't need to read JSON.
                    console.log('Refresh successful');
                    return true;
                })().finally(() => {
                    ApiClient.refreshPromise = null;
                });
            }

            try {
                // Wait for the refresh
                await ApiClient.refreshPromise;
                console.log('Retrying request...');

                // Retry original request (browser sends new access cookie)
                response = await fetch(url, options);
            } catch (error) {
                console.error('Token refresh failed:', error);

                // Redirect logic
                const loginUrl = '/accounts/login/?next=' + encodeURIComponent(window.location.pathname);
                window.location.href = loginUrl;

                // Return a Promise that NEVER resolves.
                // This prevents the calling function (e.g. Dashboard.html) from receiving a response
                // and showing an error state while the browser is navigating away.
                return new Promise(() => { });
            }
        }

        return response;
    }
};

// Expose globally
window.ApiClient = ApiClient;
