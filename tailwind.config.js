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
                    gold: '#FFD700',
                    navy: '#1B1F4A',
                    skyblue: '#4A90E2',
                    charcoal: '#4A4A4A',
                    yellow: '#F9E547',
                    grey: '#C0C0C0',
                    green: '#2C8C57',
                    offwhite: '#F4F4F4',
                },
            },
        },
    },
    plugins: [],
}