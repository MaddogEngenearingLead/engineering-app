export default {
  content: [new URL('./public/index.html', import.meta.url).pathname, new URL('./src/**/*.{js,jsx}', import.meta.url).pathname],
  theme: { extend: {} },
  plugins: [],
};
