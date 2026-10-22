/**
 * EduPulse Analytics - Main Frontend Application Script
 */
document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize Lucide Icons
    if (window.lucide) {
        window.lucide.createIcons();
    }

    // 2. Rotating Hero Phrases (lightweight, accessible)
    const rotatingElement = document.getElementById("rotatingBadge");
    if (rotatingElement) {
        const phrases = [
            "Apache PySpark Big Data Engine (1,000,000+ Records)",
            "Dual Marks-Based & University Grade-Based Ingestion",
            "Local-First Architecture & Zero Cloud Lock-In",
            "11-Stage Safe Import Wizard with Cryptographic Manifests",
            "Sub-Second Analytical Queries via Snappy Parquet"
        ];
        let index = 0;

        // Check if user prefers reduced motion
        const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        
        if (!prefersReducedMotion) {
            setInterval(() => {
                index = (index + 1) % phrases.length;
                rotatingElement.style.opacity = "0";
                setTimeout(() => {
                    rotatingElement.textContent = phrases[index];
                    rotatingElement.style.opacity = "1";
                }, 250);
            }, 3500);
        }
    }
});
