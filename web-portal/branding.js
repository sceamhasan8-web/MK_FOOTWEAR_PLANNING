/**
 * MK Footwear Planning - Centralized Branding Configuration
 * Single source of truth for company identity, typography, color themes, and logo assets.
 */
window.MK_BRANDING = {
    appName: "MK Footwear Planning",
    companyName: "MK Footwear Planning",
    tagline: "Plan • Produce • Deliver",
    subTitle: "Footwear Production Planning & Management",
    edition: "Industrial Enterprise Edition",
    copyright: "© 2026 MK Footwear Planning. All rights reserved.",
    assets: {
        logoPrimary: "mk-footwear-planning.svg",
        logoLight: "mk-footwear-logo-light.svg",
        logoIcon: "mk-footwear-icon.svg",
        favicon: "mk-footwear-icon.svg"
    },
    colors: {
        primaryNavy: "#153B66",
        primaryBlue: "#2563EB",
        lightBlue: "#DBEAFE",
        darkText: "#172B4D",
        neutralLight: "#F1F5F9",
        accentCyan: "#0284C7",
        borderSlate: "#E2E8F0"
    },
    applyBranding: function() {
        document.title = this.appName;
        const brandLogos = document.querySelectorAll('.brand-app-name');
        brandLogos.forEach(el => { el.textContent = this.appName; });
        const taglines = document.querySelectorAll('.brand-tagline');
        taglines.forEach(el => { el.textContent = this.tagline; });
    }
};
