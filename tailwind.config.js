/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                mentone: {
                    gold: '#FFD700',      // Uniform stripes, player sponsor posters, logo
                    navy: '#1B1F4A',      // Main uniform colour, poster background
                    skyblue: '#4A90E2',   // Turf field and accents
                    charcoal: '#4A4A4A',  // Typography and border detail on posters
                    yellow: '#F9E547',    // Banner heading and alternate kit accents
                    grey: '#C0C0C0',      // Background tones from sponsor flyer
                    green: '#2C8C57',     // Synthetic turf field
                    offwhite: '#F4F4F4',  // Contrast colour for clean layouts and text areas
                },
            },
        },
    },
    plugins: [],
}