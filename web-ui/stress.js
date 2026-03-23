
/**
 * Institutional Stress Harness
 * Generates deterministic load for UI resilience testing.
 */

window.StressHarness = class StressHarness {
    constructor() {
        this.active = new URLSearchParams(window.location.search).get('stress') === 'true';
        this.listeners = [];
        this.config = {
            normal: { eventsPerSecond: 100 },
            storm: { eventsPerSecond: 500 },
            flash_crash: { eventsPerSecond: 1000, burst: true },
        };
        this.currentLevel = 'storm';

        // Metrics
        this.metrics = {
            fps: 60,
            avgLag: 0,
            p99Lag: 0,
            avgCommit: 0,
            maxCommit: 0,
            heapUsed: 0,
            eventsPerSec: 0,
            droppedEvents: 0,
            crisisMode: false
        };

        this.history = {
            lag: [],
            commits: [],
            timestamps: []
        };

        this.running = false;
        if (this.active) {
            console.log("⚠️ STRESS HARNESS ACTIVATED ⚠️");
            this.start('storm');
        }
    }

    subscribe(callback) {
        this.listeners.push(callback);
        return () => {
            this.listeners = this.listeners.filter(l => l !== callback);
        };
    }

    emit(events) {
        // Measure Lag: Time from emission to processing (simulated)
        const now = performance.now();
        events.forEach(e => {
            e.timestamp = now;
        });

        this.listeners.forEach(l => l(events));
        this.metrics.eventsPerSec += events.length;
    }

    start(level = 'storm') {
        if (this.running) return;
        this.running = true;
        this.currentLevel = level;
        const config = this.config[level];

        console.log(`Starting Stress Engine: ${level.toUpperCase()} (${config.eventsPerSecond} events/s)`);

        // Event Generation Loop
        const tickRate = 50; // 20 ticks per second
        const eventsPerTick = config.eventsPerSecond / (1000 / tickRate);

        this.interval = setInterval(() => {
            const events = [];
            for (let i = 0; i < eventsPerTick; i++) {
                events.push(this.generateEvent());
            }
            this.emit(events);
        }, tickRate);

        // FPS Tracker
        this.startFpsTracker();

        // Memory Tracker
        this.startMemoryTracker();

        // Metrics Reset Loop
        setInterval(() => {
            this.metrics.eventsPerSec = 0; // Reset counter every second for "per second" view
        }, 1000);
    }

    stop() {
        this.running = false;
        clearInterval(this.interval);
        cancelAnimationFrame(this.rafId);
    }

    generateEvent() {
        // Deterministic-ish random symbols
        const id = Math.floor(Math.random() * 500);
        const symbol = `STRESS_${id}`; // Matches what the dashboard might expect or new ones
        const change = (Math.random() - 0.5) * 5;

        return {
            symbol: symbol,
            price: 100 + Math.random() * 1000,
            change: change,
            flash: change > 0 ? 'up' : 'down',
            timestamp: performance.now()
        };
    }

    startFpsTracker() {
        let lastTime = performance.now();
        let frames = 0;

        const loop = () => {
            frames++;
            const now = performance.now();
            if (now - lastTime >= 1000) {
                this.metrics.fps = frames;
                frames = 0;
                lastTime = now;
            }
            this.rafId = requestAnimationFrame(loop);
        };
        loop();
    }

    startMemoryTracker() {
        setInterval(() => {
            if (performance.memory) {
                this.metrics.heapUsed = Math.round(performance.memory.usedJSHeapSize / 1024 / 1024);
            }
        }, 1000);
    }

    // Called by UI when it processes the event to calculate lag
    reportLag(eventTimestamp) {
        const lag = performance.now() - eventTimestamp;
        this.history.lag.push(lag);
        if (this.history.lag.length > 100) this.history.lag.shift();

        // Calc Avg
        const total = this.history.lag.reduce((a, b) => a + b, 0);
        this.metrics.avgLag = Math.round(total / this.history.lag.length);

        // Calc P99
        const sorted = [...this.history.lag].sort((a, b) => a - b);
        this.metrics.p99Lag = Math.round(sorted[Math.floor(sorted.length * 0.99)] || 0);
    }

    reportProfiler(id, phase, actualDuration, baseDuration, startTime, commitTime) {
        // Track commit duration
        this.history.commits.push(actualDuration);
        if (this.history.commits.length > 50) this.history.commits.shift();

        const total = this.history.commits.reduce((a, b) => a + b, 0);
        this.metrics.avgCommit = (total / this.history.commits.length).toFixed(1);
        this.metrics.maxCommit = Math.max(...this.history.commits).toFixed(1);
    }
};

// Initialize
window.stressEngine = new window.StressHarness();
