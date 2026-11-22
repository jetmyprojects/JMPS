/**
 * client-side navigation (SPA behavior) for sidebar links
 */
document.addEventListener('DOMContentLoaded', () => {
    const mainWrapper = document.querySelector('.main-wrapper');

    // Make navigation function available globally
    window.navigateTo = async (href) => {
        // Filter out Auth links or external
        if (href.includes('login') || href.includes('admin')) {
            window.location.href = href;
            return;
        }
        if (!href.startsWith('/') && !href.startsWith(window.location.origin)) {
            window.location.href = href;
            return;
        }

        try {
            // Update active state based on href
            document.querySelectorAll('.navbar-nav .nav-link').forEach(el => {
                el.classList.toggle('active-link', el.getAttribute('href') === href);
            });
            document.querySelectorAll('.sidebar-item, .mobile-nav-link').forEach(el => {
                el.classList.toggle('active-sidebar', el.getAttribute('href') === href);
            });

            // Push State
            window.history.pushState({}, '', href);

            // Fetch Content
            const response = await fetch(href);
            if (!response.ok) throw new Error('Network response was not ok');

            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            const newMainWrapper = doc.querySelector('.main-wrapper');
            const newContentArea = doc.querySelector('.content-area');

            if (newMainWrapper && mainWrapper) {
                const currentSidebar = document.querySelector('.sidebar');
                const newSidebar = doc.querySelector('.sidebar');
                const hasSidebarChanged = (!!currentSidebar !== !!newSidebar);

                if (hasSidebarChanged) {
                    mainWrapper.innerHTML = newMainWrapper.innerHTML;
                } else {
                    const currentContent = document.querySelector('.content-area');
                    if (currentContent && newContentArea) {
                        currentContent.replaceWith(newContentArea);
                    } else {
                        mainWrapper.innerHTML = newMainWrapper.innerHTML;
                    }
                }

                // Re-execute scripts
                const scripts = newContentArea ? newContentArea.querySelectorAll('script') : newMainWrapper.querySelectorAll('script');
                scripts.forEach(script => {
                    const newScript = document.createElement('script');
                    Array.from(script.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
                    newScript.textContent = script.textContent;
                    document.body.appendChild(newScript);
                    // newScript.remove(); 
                });

                // Update Page Title
                const newTitle = doc.querySelector('title');
                if (newTitle) document.title = newTitle.textContent;

                // Update Header Title
                const newHeaderTitle = doc.querySelector('.brand-orange-title');
                const currentHeaderTitle = document.querySelector('.brand-orange-title');
                if (newHeaderTitle && currentHeaderTitle) {
                    currentHeaderTitle.innerHTML = newHeaderTitle.innerHTML;
                }

                // Dispatch event
                document.dispatchEvent(new CustomEvent('app:pageLoaded', { detail: { path: href } }));
            } else {
                window.location.reload();
            }

        } catch (error) {
            console.error('Navigation failed:', error);
            window.location.href = href;
        }
    };

    // Delegate event listener for sidebar items
    document.body.addEventListener('click', async (e) => {
        const link = e.target.closest('a.sidebar-item, a.mobile-nav-link, a.nav-link, a.spa-link');

        // Only handle internal links that are not # and have no special target
        if (!link || link.getAttribute('href') === '#' || link.target === '_blank') return;

        e.preventDefault();
        const href = link.getAttribute('href');
        await window.navigateTo(href);
    });

    // Handle Browser Back/Forward
    window.addEventListener('popstate', () => {
        window.location.reload(); // Simple fallback for now
    });
});
