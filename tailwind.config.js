/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./ui/admin/**/*.{html,js}",
        "./overlay.html"
    ],
    theme: {
        extend: {
            colors: {
                brand: {
                    dark: '#0f172a',
                    slate: '#1e293b',
                    red: '#ef4444',
                    blue: '#3b82f6',
                    accent: '#6366f1'
                }
            },
            animation: {
                'fade-in': 'fadeIn 0.3s ease-out',
                'slide-up': 'slideUp 0.4s ease-out'
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                slideUp: {
                    '0%': { transform: 'translateY(10px)', opacity: '0' },
                    '100%': { transform: 'translateY(0)', opacity: '1' },
                }
            }
        }
    },
    plugins: [],
}
