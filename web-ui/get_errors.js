const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  
  page.on('console', msg => {
    console.log('PAGE LOG:', msg.text());
  });
  
  page.on('pageerror', error => {
    console.log('\n=== PAGE ERROR ===\n', error.message, '\n==================\n');
  });
  
  page.on('requestfailed', request => {
    console.log('REQUEST FAILED:', request.url(), request.failure()?.errorText);
  });
  
  console.log("Navigating to http://localhost:8000...");
  
  try {
    await page.goto('http://localhost:8000', { waitUntil: 'networkidle0' });
    console.log("Page loaded. Checking for 3 seconds...");
    await new Promise(r => setTimeout(r, 3000));
  } catch (err) {
    console.log("Navigation Error:", err.message);
  }
  
  await browser.close();
  console.log("Done.");
})();
