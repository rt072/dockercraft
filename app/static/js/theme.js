const themeToggle = document.getElementById('themeToggle');
document.addEventListener('DOMContentLoaded', () => {
    const yearEl = document.getElementById('year');
    if (yearEl) yearEl.textContent = new Date().getFullYear();
});
const savedTheme = localStorage.getItem('theme');
const themeCss = document.getElementById('theme-css');

function setTheme(theme) {
    if (theme === 'dark') {
        themeCss.href = '/static/css/dark.css';
        themeToggle.textContent = '☀️';
    } else {
        themeCss.href = '/static/css/light.css';
        themeToggle.textContent = '🌙';
    }
    localStorage.setItem('theme', theme);
}

if (savedTheme === 'dark') {
    setTheme('dark');
} else {
    setTheme('light');
}

themeToggle.addEventListener('click', () => {
    const currentHref = themeCss.getAttribute('href');
    setTheme(currentHref.includes('dark.css') ? 'light' : 'dark');
});
