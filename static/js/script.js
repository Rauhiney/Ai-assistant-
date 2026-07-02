const HAS_THREE = typeof window.THREE !== 'undefined';

const CONFIG_3D = {
    scene: null,
    camera: null,
    renderer: null,
    composer: null,
    clock: HAS_THREE ? new THREE.Clock() : null,
    
    // Animation State
    particles: null,
    morphingGeometry: null,
    avatar: null,
    
    // Stats
    stats: {
        fps: 60,
        particleCount: 0,
        objectCount: 0,
        renderTime: 0,
    },
    
    // Settings
    settings: {
        particlesEnabled: true,
        morphingEnabled: true,
        autoScroll: true,
        geometry: 'sphere',
    },
    
    // Tracking
    mouse: { x: 0, y: 0 },
    raycaster: HAS_THREE ? new THREE.Raycaster() : null,
    conversationHistory: [],
    morphOverrideUntil: 0,
};

let CURRENT_BROWSER_LOCATION = null;
let BROWSER_LOCATION_PROMISE = null;
const LOCATION_STORAGE_KEY = 'denz_browser_location';

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function getSessionId() {
    const storageKey = 'denz_session_id';
    let sessionId = localStorage.getItem(storageKey);

    if (!sessionId) {
        const randomPart = Math.random().toString(36).slice(2, 10);
        sessionId = `denz-${Date.now()}-${randomPart}`;
        localStorage.setItem(storageKey, sessionId);
    }

    return sessionId;
}

/**
 * Check if Ollama AI is ready
 */
let OLLAMA_STATUS = {
    ready: false,
    checking: true,
    lastCheck: 0,
};

async function checkOllamaReady() {
    try {
        const response = await fetch('/api/ollama/ready', { timeout: 3000 });
        OLLAMA_STATUS.ready = response.status === 200;
        OLLAMA_STATUS.checking = false;
        OLLAMA_STATUS.lastCheck = Date.now();
        
        if (OLLAMA_STATUS.ready) {
            console.log('✅ Ollama is ready!');
            updateOllamaIndicator(true);
        } else {
            console.log('⏳ Ollama is starting up...');
            updateOllamaIndicator(false);
        }
    } catch (error) {
        console.log('⏳ Checking Ollama...', error.message);
        OLLAMA_STATUS.ready = false;
        OLLAMA_STATUS.checking = false;
        updateOllamaIndicator(false);
    }
}

function updateOllamaIndicator(isReady) {
    const indicator = document.getElementById('ollama-status-indicator');
    if (!indicator) return;
    
    if (isReady) {
        indicator.className = 'ollama-indicator ready';
        indicator.title = 'Ollama AI is ready';
        indicator.innerHTML = '<span class="dot"></span> Ready';
    } else {
        indicator.className = 'ollama-indicator loading';
        indicator.title = 'Ollama AI is warming up...';
        indicator.innerHTML = '<span class="dot"></span> Warming up';
    }
}

// Start checking Ollama status on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        checkOllamaReady();
        // Re-check every 5 seconds if not ready
        const checkInterval = setInterval(() => {
            if (!OLLAMA_STATUS.ready) {
                checkOllamaReady();
            } else {
                clearInterval(checkInterval);
            }
        }, 5000);
    });
} else {
    checkOllamaReady();
}

/**
 * Initialize Gradient Canvas Background
 */
function initGradientCanvas() {
    let canvas = document.getElementById('gradient-canvas');
    if (!canvas) {
        const backgroundContainer = document.createElement('div');
        backgroundContainer.className = 'background-container generated-background';

        const starfield = document.createElement('div');
        starfield.className = 'starfield';

        canvas = document.createElement('canvas');
        canvas.id = 'gradient-canvas';

        backgroundContainer.appendChild(starfield);
        backgroundContainer.appendChild(canvas);
        document.body.prepend(backgroundContainer);
    }

    const ctx = canvas.getContext('2d');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let width = 0;
    let height = 0;
    let stars = [];
    let rockets = [];

    const resizeCanvas = () => {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = width * window.devicePixelRatio;
        canvas.height = height * window.devicePixelRatio;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);

        const starCount = Math.min(240, Math.floor((width * height) / 5200));
        stars = Array.from({ length: starCount }, () => ({
            x: Math.random() * width,
            y: Math.random() * height,
            size: 0.4 + Math.random() * 1.8,
            alpha: 0.22 + Math.random() * 0.72,
            twinkle: 0.35 + Math.random() * 1.8,
        }));

        const rocketCount = width < 720 ? 4 : 8;
        rockets = Array.from({ length: rocketCount }, (_, index) => ({
            x: Math.random() * width,
            y: Math.random() * height,
            speed: 0.22 + Math.random() * 0.34,
            size: 0.42 + Math.random() * 0.34,
            offset: index * 0.7,
        }));
    };

    const drawMilkyWay = (time) => {
        ctx.save();
        ctx.translate(width * 0.52, height * 0.48);
        ctx.rotate(-0.42);

        const galaxy = ctx.createLinearGradient(-width * 0.65, 0, width * 0.65, 0);
        galaxy.addColorStop(0, 'rgba(74, 158, 255, 0)');
        galaxy.addColorStop(0.22, 'rgba(74, 158, 255, 0.1)');
        galaxy.addColorStop(0.48, 'rgba(255, 255, 255, 0.18)');
        galaxy.addColorStop(0.66, 'rgba(255, 107, 157, 0.11)');
        galaxy.addColorStop(1, 'rgba(0, 255, 136, 0)');

        ctx.globalAlpha = 0.82;
        ctx.fillStyle = galaxy;
        ctx.filter = 'blur(18px)';
        ctx.fillRect(-width, -height * 0.16, width * 2, height * 0.32);

        ctx.globalAlpha = 0.38 + Math.sin(time * 0.00025) * 0.08;
        ctx.filter = 'blur(42px)';
        ctx.fillRect(-width * 0.75, -height * 0.06, width * 1.5, height * 0.12);
        ctx.restore();
        ctx.filter = 'none';
    };

    const drawRocket = (rocket, time) => {
        const drift = reduceMotion ? 0 : time * rocket.speed * 0.035;
        const x = (rocket.x + drift) % (width + 90) - 45;
        const y = (rocket.y - drift * 0.38 + Math.sin(time * 0.001 + rocket.offset) * 10 + height + 60) % (height + 120) - 60;
        const scale = rocket.size;

        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(-0.82);
        ctx.scale(scale, scale);

        ctx.fillStyle = 'rgba(0, 255, 136, 0.58)';
        ctx.beginPath();
        ctx.moveTo(-18, 0);
        ctx.lineTo(-32, -5);
        ctx.lineTo(-32, 5);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = '#ff6b9d';
        ctx.beginPath();
        ctx.moveTo(18, 0);
        ctx.lineTo(7, -7);
        ctx.lineTo(7, 7);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = '#4a9eff';
        ctx.beginPath();
        ctx.moveTo(-8, -6);
        ctx.lineTo(4, -6);
        ctx.quadraticCurveTo(10, -6, 10, 0);
        ctx.quadraticCurveTo(10, 6, 4, 6);
        ctx.lineTo(-8, 6);
        ctx.quadraticCurveTo(-14, 6, -14, 0);
        ctx.quadraticCurveTo(-14, -6, -8, -6);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = 'rgba(255, 255, 255, 0.95)';
        ctx.beginPath();
        ctx.arc(1, 0, 3, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#ff6b9d';
        ctx.beginPath();
        ctx.moveTo(-10, -6);
        ctx.lineTo(-18, -13);
        ctx.lineTo(-15, -4);
        ctx.closePath();
        ctx.fill();

        ctx.beginPath();
        ctx.moveTo(-10, 6);
        ctx.lineTo(-18, 13);
        ctx.lineTo(-15, 4);
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    };

    const drawSpaceBackground = (time) => {
        ctx.clearRect(0, 0, width, height);

        const base = ctx.createRadialGradient(width * 0.5, height * 0.45, 0, width * 0.5, height * 0.45, Math.max(width, height));
        base.addColorStop(0, 'rgba(10, 14, 39, 0.82)');
        base.addColorStop(0.48, 'rgba(4, 6, 20, 0.96)');
        base.addColorStop(1, 'rgba(0, 0, 0, 1)');
        ctx.fillStyle = base;
        ctx.fillRect(0, 0, width, height);

        drawMilkyWay(time);

        stars.forEach((star) => {
            const twinkle = reduceMotion ? 1 : 0.65 + Math.sin(time * 0.001 * star.twinkle + star.x) * 0.35;
            ctx.globalAlpha = star.alpha * twinkle;
            ctx.fillStyle = '#ffffff';
            ctx.beginPath();
            ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.globalAlpha = 1;

        rockets.forEach((rocket) => drawRocket(rocket, time));

        requestAnimationFrame(drawSpaceBackground);
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    requestAnimationFrame(drawSpaceBackground);
}
/**
 * Fetch API Data
 */
async function fetchAPI(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        
        if (!response.ok) throw new Error(`API Error: ${response.status} ${response.statusText}`);
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        return null;
    }
}

/**
 * Show Toast Notification
 */
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container-3d') || document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast-3d toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        background: rgba(74, 158, 255, 0.9);
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        margin-bottom: 10px;
        animation: float-up 0.3s ease-out;
    `;
    
    container.appendChild(toast);
    setTimeout(() => toast.remove(), duration);
}

/**
 * Format Time
 */
function formatTime() {
    const now = new Date();
    return now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Linear Interpolation
 */
function lerp(a, b, t) {
    return a + (b - a) * t;
}

/**
 * Ease Functions
 */
const easing = {
    easeInOutCubic: (t) => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2,
    easeInOutQuad: (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t,
    easeOutQuart: (t) => 1 - Math.pow(1 - t, 4),
};

function disposeScene() {
    if (!CONFIG_3D.scene) return;

    CONFIG_3D.scene.traverse((object) => {
        if (object.geometry) {
            object.geometry.dispose();
        }

        if (object.material) {
            if (Array.isArray(object.material)) {
                object.material.forEach(mat => mat.dispose());
            } else {
                object.material.dispose();
            }
        }
    });

    if (CONFIG_3D.renderer) {
        CONFIG_3D.renderer.dispose();
    }

    while (CONFIG_3D.scene.children.length > 0) {
        CONFIG_3D.scene.remove(CONFIG_3D.scene.children[0]);
    }
}

window.addEventListener('beforeunload', disposeScene);
// ============================================================================
// THREE.JS SHADER MATERIALS
// ============================================================================

/**
 * Create Morphing Shader Material
 */
function createMorphingShaderMaterial() {
    const vertexShader = `
        uniform float uTime;
        uniform float uMorphFactor;
        uniform float uNoiseScale;
        
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying float vNoise;
        
        // 2D Simplex noise
        vec3 permute(vec3 x) { return mod(((x*34.0)+1.0)*x, 289.0); }
        float snoise(vec2 v) {
            const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
            vec2 i  = floor(v + dot(v, C.yy) );
            vec2 x0 = v -   i + dot(i, C.xx);
            vec2 x12;
            x12.x = x0.x + C.xx;
            x12.y = x0.y + C.xx;
            i = mod(i, 289.0);
            vec3 p = permute( permute( i.y + vec3(0.0, C.xx)) + i.x + vec3(0.0, x0.x, x12.x) );
            vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.x,x12.x), dot(x12.y,x12.y) ), 0.0);
            m = m*m ;
            m = m*m ;
            vec3 x = 2.0 * fract(p * C.www) - 1.0;
            vec3 h = abs(x) - 0.5;
            vec3 ox = floor(x + 0.5);
            vec3 a0x = x - ox;
            m *= 1.79284291400159 - 0.85373472095314 * ( a0x*a0x + h*h );
            vec3 g;
            g.x  = a0x.x  * x0.x  + h.x  * x0.y;
            g.yz = a0x.yz * x12.xy + h.yz * x12.zy;
            return 130.0 * dot(m, g);
        }
        
        void main() {
            vNormal = normalize(normalMatrix * normal);
            
            vec3 pos = position;
            
            // Apply morphing
            pos *= mix(1.0, 1.2, uMorphFactor);
            
            // Add noise animation
            float noise = snoise(vec2(position.x, position.y) * uNoiseScale + uTime * 0.5);
            pos += normal * noise * 0.1;
            
            vNoise = noise;
            vPosition = vec3(modelMatrix * vec4(pos, 1.0));
            
            gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
        }
    `;
    
    const fragmentShader = `
        uniform float uTime;
        
        varying vec3 vNormal;
        varying vec3 vPosition;
        varying float vNoise;
        
        void main() {
            // Base color
            vec3 color = vec3(0.29, 0.61, 1.0);
            
            // Glow effect
            float glow = 0.5 + 0.5 * sin(uTime * 2.0 + vNoise * 5.0);
            
            // Fresnel effect
            vec3 viewDir = normalize(cameraPosition - vPosition);
            float fresnel = pow(1.0 - abs(dot(viewDir, vNormal)), 3.0);
            
            color += fresnel * vec3(1.0, 0.4, 0.8) * 0.5;
            color += glow * 0.2;
            
            gl_FragColor = vec4(color, 0.9);
        }
    `;
    
    return new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
            uMorphFactor: { value: 0 },
            uNoiseScale: { value: 0.01 },
        },
        vertexShader,
        fragmentShader,
        transparent: true,
        wireframe: false,
    });
}

/**
 * Create Particle Shader Material
 */
function createParticleShaderMaterial() {
    const vertexShader = `
        attribute vec3 velocity;
        attribute float life;
        attribute float size;
        
        uniform float uTime;
        
        varying float vLife;
        varying vec3 vColor;
        
        void main() {
            vLife = life;
            
            // Color based on life
            vColor = mix(
                vec3(0.29, 0.61, 1.0),
                vec3(1.0, 0.42, 0.62),
                life
            );
            
            // Animation
            vec3 pos = position + velocity * uTime;
            
            gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
            gl_PointSize = size * (1.0 - life) * 14.0;
        }
    `;
    
    const fragmentShader = `
        varying float vLife;
        varying vec3 vColor;
        
        void main() {
            vec2 coord = gl_PointCoord - 0.5;
            float radius = length(coord);

            if (radius > 0.5) discard;

            float core = 1.0 - smoothstep(0.0, 0.22, radius);
            float horizontalRay = (1.0 - smoothstep(0.015, 0.11, abs(coord.y))) * (1.0 - smoothstep(0.05, 0.5, abs(coord.x)));
            float verticalRay = (1.0 - smoothstep(0.015, 0.11, abs(coord.x))) * (1.0 - smoothstep(0.05, 0.5, abs(coord.y)));
            float diagonalRayA = (1.0 - smoothstep(0.0, 0.075, abs(coord.x - coord.y))) * (1.0 - smoothstep(0.05, 0.5, radius));
            float diagonalRayB = (1.0 - smoothstep(0.0, 0.075, abs(coord.x + coord.y))) * (1.0 - smoothstep(0.05, 0.5, radius));
            float halo = (1.0 - smoothstep(0.0, 0.5, radius)) * 0.32;

            float star = max(core, max(horizontalRay, verticalRay) * 0.85);
            star = max(star, max(diagonalRayA, diagonalRayB) * 0.36);
            star += halo;

            float sparkle = 0.72 + 0.28 * sin((gl_FragCoord.x + gl_FragCoord.y) * 0.08);
            float alpha = clamp(star * vLife * sparkle, 0.0, 1.0);
            vec3 glowColor = mix(vec3(1.0), vColor, 0.58);
            gl_FragColor = vec4(glowColor, alpha);
        }
    `;
    
    return new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
        },
        vertexShader,
        fragmentShader,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
    });
}

// ============================================================================
// 3D SCENE INITIALIZATION
// ============================================================================

/**
 * Initialize 3D Scene
 */
function init3DScene(containerId) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container ${containerId} not found`);
        return false;
    }

    if (!HAS_THREE) {
        console.error('Three.js failed to load');
        showToast('3D library failed to load. Check your internet connection and refresh.', 'error', 5000);
        return false;
    }

    if (!window.WebGLRenderingContext) {
        console.error('WebGL is not supported in this browser');
        showToast('WebGL is not supported in this browser.', 'error', 5000);
        return false;
    }
    
    const isLightTheme = document.body.classList.contains('light-mode');
    const sceneBackground = isLightTheme ? 0xf7fbff : 0x000000;

    // Scene setup
    CONFIG_3D.scene = new THREE.Scene();
    CONFIG_3D.scene.background = isLightTheme ? new THREE.Color(sceneBackground) : null;
    CONFIG_3D.scene.fog = new THREE.Fog(sceneBackground, 100, 1000);
    
    // Camera setup
    CONFIG_3D.camera = new THREE.PerspectiveCamera(
        75,
        container.clientWidth / container.clientHeight,
        0.1,
        1000
    );
    CONFIG_3D.camera.position.set(0, 2, 5);
    
    // Renderer setup
    CONFIG_3D.renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
    });
    CONFIG_3D.renderer.setSize(container.clientWidth, container.clientHeight);
    CONFIG_3D.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    CONFIG_3D.renderer.shadowMap.enabled = false;
    CONFIG_3D.renderer.outputColorSpace = THREE.SRGBColorSpace;
    CONFIG_3D.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    
    container.appendChild(CONFIG_3D.renderer.domElement);
    
    // Setup lighting
    setupLights();
    
    // Setup geometry
    createMorphingGeometry();
    createParticleSystem();
    createAvatar();
    
    // Event listeners
    window.addEventListener('resize', onWindowResize);
    document.addEventListener('mousemove', onMouseMove);
    
    // Start animation loop
    animate();
    
    return true;
}

/**
 * Setup Lighting
 */
function setupLights() {
    // Ambient light
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    CONFIG_3D.scene.add(ambientLight);
    
    // Main directional light
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(5, 10, 7);
    dirLight.castShadow = false;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    CONFIG_3D.scene.add(dirLight);
    
    // Fill light
    const fillLight = new THREE.DirectionalLight(0x4488ff, 0.4);
    fillLight.position.set(-5, 5, -5);
    CONFIG_3D.scene.add(fillLight);
    
    // Rim light
    const rimLight = new THREE.DirectionalLight(0xff6b9d, 0.3);
    rimLight.position.set(0, 10, -10);
    CONFIG_3D.scene.add(rimLight);
    
    // Point light
    const pointLight = new THREE.PointLight(0x00ff88, 1, 50);
    pointLight.position.set(0, 2, 5);
    CONFIG_3D.scene.add(pointLight);
}

/**
 * Create Morphing Geometry
 */
function createMorphingGeometry() {
    // Create base geometry
    let geometry;
    
    switch(CONFIG_3D.settings.geometry) {
        case 'octahedron':
            geometry = new THREE.OctahedronGeometry(2.25, 0);
            break;
        case 'torus':
            geometry = new THREE.TorusGeometry(1.65, 0.55, 18, 64);
            break;
        case 'icosahedron':
            geometry = new THREE.IcosahedronGeometry(2.25, 0);
            break;
        case 'tetrahedron':
            geometry = new THREE.TetrahedronGeometry(2.45, 0);
            break;
        default:
            geometry = new THREE.SphereGeometry(2, 32, 32);
    }
    
    // Create shader material
    const material = createMorphingShaderMaterial();
    
    // Create mesh
    CONFIG_3D.morphingGeometry = new THREE.Mesh(geometry, material);
    CONFIG_3D.morphingGeometry.castShadow = false;
    CONFIG_3D.morphingGeometry.visible = true;
    CONFIG_3D.morphingGeometry.scale.set(1.35, 1.35, 1.35);
    CONFIG_3D.scene.add(CONFIG_3D.morphingGeometry);
}

function formatShapeName(shape) {
    return shape.charAt(0).toUpperCase() + shape.slice(1);
}

function setAvatarStatus(status) {
    const statusElement = document.getElementById('avatar-status');
    if (statusElement) {
        statusElement.textContent = status;
    }
}

function replaceMorphingGeometry(shape) {
    if (!HAS_THREE || !CONFIG_3D.scene) return false;

    CONFIG_3D.settings.geometry = shape;

    if (CONFIG_3D.morphingGeometry) {
        CONFIG_3D.scene.remove(CONFIG_3D.morphingGeometry);
        CONFIG_3D.morphingGeometry.geometry.dispose();
        CONFIG_3D.morphingGeometry.material.dispose();
        CONFIG_3D.morphingGeometry = null;
    }

    createMorphingGeometry();

    CONFIG_3D.morphingGeometry.scale.set(1.35, 1.35, 1.35);
    CONFIG_3D.morphingGeometry.rotation.set(0, 0, 0);
    setAvatarStatus(`${formatShapeName(shape)} shape`);

    if (typeof gsap !== 'undefined') {
        gsap.fromTo(
            CONFIG_3D.morphingGeometry.scale,
            { x: 0.9, y: 0.9, z: 0.9 },
            { x: 1.35, y: 1.35, z: 1.35, duration: 0.35, ease: 'back.out(1.7)' }
        );
    }

    showToast(`3D shape changed to ${formatShapeName(shape)}`, 'info', 1600);
    return true;
}

function runMorphEffect() {
    if (!CONFIG_3D.morphingGeometry || !CONFIG_3D.morphingGeometry.material.uniforms) return;

    CONFIG_3D.settings.morphingEnabled = true;
    CONFIG_3D.morphOverrideUntil = performance.now() + 1400;

    const morphToggle = document.getElementById('morph-toggle');
    if (morphToggle) {
        morphToggle.checked = true;
    }

    const uniforms = CONFIG_3D.morphingGeometry.material.uniforms;
    setAvatarStatus('Morphing');

    if (typeof gsap !== 'undefined') {
        gsap.killTweensOf(uniforms.uMorphFactor);
        gsap.killTweensOf(CONFIG_3D.morphingGeometry.scale);
        gsap.killTweensOf(CONFIG_3D.morphingGeometry.rotation);

        gsap.timeline({
            onComplete: () => setAvatarStatus(`${formatShapeName(CONFIG_3D.settings.geometry)} shape`),
        })
            .to(uniforms.uMorphFactor, { value: 1, duration: 0.35, ease: 'power2.out' }, 0)
            .to(uniforms.uMorphFactor, { value: 0.15, duration: 0.55, ease: 'power2.inOut' }, 0.35)
            .to(CONFIG_3D.morphingGeometry.scale, {
                x: 1.75,
                y: 1.75,
                z: 1.75,
                duration: 0.35,
                yoyo: true,
                repeat: 1,
                ease: 'back.out(1.7)',
            }, 0)
            .to(CONFIG_3D.morphingGeometry.rotation, {
                x: '+=0.8',
                y: '+=1.4',
                duration: 0.8,
                ease: 'power2.out',
            }, 0);
    } else {
        uniforms.uMorphFactor.value = 1;
        CONFIG_3D.morphingGeometry.scale.set(1.75, 1.75, 1.75);
        setTimeout(() => {
            if (!CONFIG_3D.morphingGeometry) return;
            uniforms.uMorphFactor.value = 0.15;
            CONFIG_3D.morphingGeometry.scale.set(1.35, 1.35, 1.35);
            setAvatarStatus(`${formatShapeName(CONFIG_3D.settings.geometry)} shape`);
        }, 700);
    }

    showToast('Morph effect activated', 'info', 1400);
}

/**
 * Create Particle System
 */
function createParticleSystem() {
    const particleCount = 1500;
    const geometry = new THREE.BufferGeometry();
    
    const positions = new Float32Array(particleCount * 3);
    const velocities = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);
    const lives = new Float32Array(particleCount);
    
    for (let i = 0; i < particleCount; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 40;
        
        velocities[i * 3] = (Math.random() - 0.5) * 0.5;
        velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.5;
        velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.5;
        
        sizes[i] = Math.random() * 2 + 0.5;
        lives[i] = Math.random();
    }
    
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('velocity', new THREE.BufferAttribute(velocities, 3));
    geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    geometry.setAttribute('life', new THREE.BufferAttribute(lives, 1));
    
    const material = createParticleShaderMaterial();
    CONFIG_3D.particles = new THREE.Points(geometry, material);
    CONFIG_3D.scene.add(CONFIG_3D.particles);
}

/**
 * Create 3D Avatar
 */
function createAvatar() {
    const group = new THREE.Group();

    const bodyMaterial = new THREE.MeshStandardMaterial({
        color: 0x4a9eff,
        metalness: 0.45,
        roughness: 0.32,
        emissive: 0x1a4d99,
        emissiveIntensity: 0.08,
    });
    const noseMaterial = new THREE.MeshStandardMaterial({
        color: 0xff6b9d,
        metalness: 0.25,
        roughness: 0.38,
    });
    const glassMaterial = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0x00ff88,
        emissiveIntensity: 0.85,
        metalness: 0.1,
        roughness: 0.18,
    });
    const flameMaterial = new THREE.MeshStandardMaterial({
        color: 0x00ff88,
        emissive: 0x00ff88,
        emissiveIntensity: 1.2,
        transparent: true,
        opacity: 0.85,
    });

    const fuselage = new THREE.Mesh(
        new THREE.CylinderGeometry(0.34, 0.42, 1.45, 40),
        bodyMaterial
    );
    fuselage.position.y = 0.1;
    group.add(fuselage);

    const noseCone = new THREE.Mesh(
        new THREE.ConeGeometry(0.34, 0.62, 40),
        noseMaterial
    );
    noseCone.position.y = 1.14;
    group.add(noseCone);

    const window = new THREE.Mesh(
        new THREE.SphereGeometry(0.15, 24, 24),
        glassMaterial
    );
    window.scale.set(1, 1, 0.32);
    window.position.set(0, 0.45, 0.37);
    group.add(window);

    const engine = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28, 0.36, 0.18, 32),
        new THREE.MeshStandardMaterial({
            color: 0x2a5a9f,
            metalness: 0.5,
            roughness: 0.35,
        })
    );
    engine.position.y = -0.72;
    group.add(engine);

    const finGeometry = new THREE.ConeGeometry(0.22, 0.58, 3);
    const finMaterial = new THREE.MeshStandardMaterial({
        color: 0xff6b9d,
        metalness: 0.2,
        roughness: 0.42,
    });

    const leftFin = new THREE.Mesh(finGeometry, finMaterial);
    leftFin.position.set(-0.4, -0.48, 0);
    leftFin.rotation.z = Math.PI;
    leftFin.rotation.y = Math.PI / 2;
    leftFin.scale.set(0.8, 1, 0.7);
    group.add(leftFin);

    const rightFin = leftFin.clone();
    rightFin.position.x = 0.4;
    rightFin.rotation.y = -Math.PI / 2;
    group.add(rightFin);

    const rearFin = new THREE.Mesh(finGeometry, finMaterial);
    rearFin.position.set(0, -0.48, -0.36);
    rearFin.rotation.z = Math.PI;
    rearFin.scale.set(0.75, 1, 0.7);
    group.add(rearFin);

    const flame = new THREE.Mesh(
        new THREE.ConeGeometry(0.24, 0.55, 24),
        flameMaterial
    );
    flame.name = 'rocket-flame';
    flame.position.y = -1.08;
    flame.rotation.x = Math.PI;
    group.add(flame);

    group.scale.set(1.05, 1.05, 1.05);
    
    CONFIG_3D.avatar = group;
    CONFIG_3D.scene.add(group);
    setAvatarStatus('Rocket ready');
}

// ============================================================================
// ANIMATION & RENDERING
// ============================================================================

/**
 * Main Animation Loop
 */
function animate() {
    requestAnimationFrame(animate);
    
    const deltaTime = CONFIG_3D.clock.getDelta();
    const elapsed = CONFIG_3D.clock.getElapsedTime();
    
    // Update morphing geometry
    if (CONFIG_3D.morphingGeometry && CONFIG_3D.morphingGeometry.material.uniforms) {
        CONFIG_3D.morphingGeometry.material.uniforms.uTime.value = elapsed;
        if (performance.now() > CONFIG_3D.morphOverrideUntil) {
            CONFIG_3D.morphingGeometry.material.uniforms.uMorphFactor.value =
                CONFIG_3D.settings.morphingEnabled
                    ? 0.45 + 0.45 * Math.sin(elapsed * 1.15)
                    : 0;
        }
        
        // Rotation
        CONFIG_3D.morphingGeometry.rotation.x += deltaTime * 0.25;
        CONFIG_3D.morphingGeometry.rotation.y += deltaTime * 0.5;
    }
    
    // Update particles
    if (CONFIG_3D.particles && CONFIG_3D.particles.material.uniforms) {
        CONFIG_3D.particles.material.uniforms.uTime.value = elapsed;
        CONFIG_3D.particles.rotation.x += 0.0001;
        CONFIG_3D.particles.rotation.y += 0.0002;
    }
    
    // Update avatar
    if (CONFIG_3D.avatar) {
        CONFIG_3D.avatar.position.y = 0.05 * Math.sin(elapsed * 0.5);
        CONFIG_3D.avatar.rotation.y += deltaTime * 0.5;
        const flame = CONFIG_3D.avatar.getObjectByName('rocket-flame');
        if (flame) {
            const flamePulse = 0.85 + 0.2 * Math.sin(elapsed * 12);
            flame.scale.set(flamePulse, 1 + 0.18 * Math.sin(elapsed * 14), flamePulse);
        }
    }
    
    // Update camera
    CONFIG_3D.camera.position.x += (CONFIG_3D.mouse.x * 0.5 - CONFIG_3D.camera.position.x) * 0.05;
    CONFIG_3D.camera.position.y += (CONFIG_3D.mouse.y * 0.3 + 2 - CONFIG_3D.camera.position.y) * 0.05;
    CONFIG_3D.camera.lookAt(0, 0, 0);
    
    // Render
    CONFIG_3D.renderer.render(CONFIG_3D.scene, CONFIG_3D.camera);
    
    // Update stats
    updateStats();
}

/**
 * Update Statistics
 */
let frameCount = 0;
let lastFpsUpdate = performance.now();

function updateStats() {
    frameCount++;

    const now = performance.now();

    if (now - lastFpsUpdate >= 1000) {
        const fps = Math.round((frameCount * 1000) / (now - lastFpsUpdate));

        frameCount = 0;
        lastFpsUpdate = now;

        const fpsElement =
            document.getElementById('fps-count') ||
            document.getElementById('avatar-fps');

        const particleElement =
            document.getElementById('particle-count') ||
            document.getElementById('avatar-particles');

        const objectElement =
            document.getElementById('object-count');

        if (fpsElement) fpsElement.textContent = fps;
        if (particleElement) particleElement.textContent = '1500';

        if (objectElement) {
            objectElement.textContent =
                CONFIG_3D.scene ? CONFIG_3D.scene.children.length : 0;
        }
    }
}

/**
 * Window Resize Handler
 */
function onWindowResize() {
    if (!CONFIG_3D.renderer || !CONFIG_3D.camera) return;

    const container = CONFIG_3D.renderer.domElement.parentElement;
    const width = container.clientWidth;
    const height = container.clientHeight;
    
    CONFIG_3D.camera.aspect = width / height;
    CONFIG_3D.camera.updateProjectionMatrix();
    CONFIG_3D.renderer.setSize(width, height);
}

/**
 * Mouse Move Handler
 */
function onMouseMove(event) {
    CONFIG_3D.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    CONFIG_3D.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
}

// ============================================================================
// UI INTERACTIONS
// ============================================================================

/**
 * Setup Theme Toggle
 */
function setupThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;
    
    const isDarkMode = localStorage.getItem('theme') !== 'light';
    
    if (!isDarkMode) {
        document.body.classList.add('light-mode');
        themeToggle.textContent = '☀️';
    }
    
    themeToggle.addEventListener('click', (e) => {
        e.preventDefault();
        document.body.classList.toggle('light-mode');
        const isLight = document.body.classList.contains('light-mode');
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        themeToggle.textContent = isLight ? '☀️' : '🌙';
    });
}

function setupThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');
    if (!themeToggle) return;

    const sunIcon = '\u2600\uFE0F';
    const moonIcon = '\uD83C\uDF19';

    const applyTheme = (theme) => {
        const isLight = theme === 'light';
        document.body.classList.toggle('light-mode', isLight);
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        themeToggle.textContent = isLight ? sunIcon : moonIcon;
        themeToggle.setAttribute('aria-label', isLight ? 'Switch to dark mode' : 'Switch to light mode');

        if (CONFIG_3D.scene) {
            const backgroundColor = isLight ? 0xf7fbff : 0x000000;
            CONFIG_3D.scene.background = isLight ? new THREE.Color(backgroundColor) : null;
            CONFIG_3D.scene.fog = new THREE.Fog(backgroundColor, 100, 1000);
        }
    };

    applyTheme(localStorage.getItem('theme') === 'light' ? 'light' : 'dark');

    themeToggle.addEventListener('click', (e) => {
        e.preventDefault();
        const nextTheme = document.body.classList.contains('light-mode') ? 'dark' : 'light';
        applyTheme(nextTheme);
    });
}

/**
 * Setup Responsive Navigation
 */
function setupResponsiveNav() {
    const hamburger = document.querySelector('.hamburger');
    const navMenu = document.querySelector('.nav-menu');
    
    if (!hamburger || !navMenu) return;
    
    hamburger.addEventListener('click', () => {
        hamburger.classList.toggle('active');
        navMenu.classList.toggle('active');
    });
    
    const navLinks = navMenu.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            hamburger.classList.remove('active');
            navMenu.classList.remove('active');
        });
    });
}

/**
 * Setup Chat Interface
 */
function setupChatInterface() {
    const input = document.getElementById('chat-input-3d');
    const sendBtn = document.getElementById('send-btn-3d');
    const voiceBtn = document.getElementById('voice-btn');
    const messagesContainer = document.getElementById('chat-messages-3d');
    
    if (!sendBtn) return;

    let isSending = false;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'en-US';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
            if (voiceBtn) {
                voiceBtn.classList.add('listening');
                voiceBtn.setAttribute('aria-pressed', 'true');
            }
            if (input) {
                input.placeholder = 'Listening... Speak now';
            }
        };

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(result => result[0]?.transcript || '')
                .join(' ')
                .trim();

            if (transcript) {
                input.value = transcript;
                handleSend();
            }
        };

        recognition.onerror = (event) => {
            console.error('Voice recognition error:', event.error);
            showToast('Voice recognition failed. Please try again.', 'error', 4000);
            if (voiceBtn) {
                voiceBtn.classList.remove('listening');
                voiceBtn.setAttribute('aria-pressed', 'false');
            }
            if (input) {
                input.placeholder = 'Type to chat with DENZ...';
            }
        };

        recognition.onend = () => {
            if (voiceBtn) {
                voiceBtn.classList.remove('listening');
                voiceBtn.setAttribute('aria-pressed', 'false');
            }
            if (input) {
                input.placeholder = 'Type to chat with DENZ...';
            }
        };
    }
    
    const handleSend = async () => {
        if (isSending) return;
        const message = input.value.trim();
        if (!message) return;

        isSending = true;
        sendBtn.disabled = true;
        
        // Add user message
        addMessage(message, 'user');
        input.value = '';
        
        // Get response
        try {
            const messageLooksLocationAware = /\b(weather|temperature|forecast|rain|humidity|location|where am i|near me|map)\b/i.test(message);
            const browserLocation = CURRENT_BROWSER_LOCATION
                || loadCachedBrowserLocation()
                || await detectBrowserLocation({
                    timeout: messageLooksLocationAware ? 10000 : 5000,
                    silent: !messageLooksLocationAware,
                });

            const response = await fetchAPI('/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message,
                    session_id: getSessionId(),
                    location: browserLocation,
                }),
            });
            
            if (response && response.success) {
                addMessage(response.response, 'bot');
                updateMiniMap(response.location);
                updateGeolocationInterface(response.location, {
                    status: 'Updated from chat context',
                });
                
                // Trigger 3D effect
                if (response['3d_effect']) {
                    trigger3DEffect(response['3d_effect']);
                }
            } else {
                addMessage('I could not reach the DENZ backend. Please check that the deployed backend is running and that /api/health works on this same website.', 'bot');
                showToast('Backend connection failed', 'error', 4000);
            }
        } finally {
            isSending = false;
            sendBtn.disabled = false;
        }
    };
    
    sendBtn.addEventListener('click', handleSend);
    if (voiceBtn && recognition) {
        voiceBtn.addEventListener('click', () => {
            if (voiceBtn.classList.contains('listening')) {
                recognition.stop();
                return;
            }

            if (input) {
                input.focus();
            }
            recognition.start();
        });
    } else if (voiceBtn) {
        voiceBtn.addEventListener('click', () => {
            showToast('Voice recognition is not supported in this browser.', 'error', 4000);
        });
    }

    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSend();
    });
    
    // Character count
    input.addEventListener('input', () => {
        const charCount = document.getElementById('char-count');
        if (charCount) charCount.textContent = `${input.value.length}/500`;
    });
}

async function loadChatHistory() {
    const container = document.getElementById('chat-messages-3d');
    if (!container) return;

    const response = await fetchAPI(`/api/chat/history?session_id=${encodeURIComponent(getSessionId())}&limit=50`);
    if (!response || !response.success || !response.history || response.history.length === 0) return;

    const welcome = container.querySelector('.chat-welcome-3d');
    if (welcome) welcome.remove();
    response.history.forEach((message) => {
        addMessage(message.user, 'user');
        addMessage(message.bot, 'bot');
    });
}

function setupAuthControls() {
    const authBtn = document.getElementById('auth-btn');
    const modal = document.getElementById('auth-modal');
    const closeBtn = document.getElementById('auth-modal-close');
    const form = document.getElementById('auth-form');
    const loginTab = document.getElementById('login-tab');
    const registerTab = document.getElementById('register-tab');
    const emailInput = document.getElementById('auth-email');
    const phoneInput = document.getElementById('auth-phone');
    const otpChannelInput = document.getElementById('auth-otp-channel');
    const otpInput = document.getElementById('auth-otp');
    const usernameInput = document.getElementById('auth-username');
    const passwordInput = document.getElementById('auth-password');
    const newPasswordInput = document.getElementById('auth-new-password');
    const title = document.getElementById('auth-modal-title');
    const adminLink = document.getElementById('admin-nav-link');
    const status = document.getElementById('auth-status');
    const submitBtn = form ? form.querySelector('.auth-submit') : null;
    const forgotBtn = document.getElementById('forgot-auth-btn');
    const gatedLinks = document.querySelectorAll('[data-auth-trigger]');
    if (!authBtn && !modal && gatedLinks.length === 0) return;

    let authMode = 'login';
    let currentUser = null;
    let pendingRedirect = null;
    let otpPending = false;
    let registrationContactVerified = false;
    let recoveryPending = false;

    if (form) {
        form.noValidate = true;
    }

    const syncRegisterContactFields = () => {
        if (authMode !== 'register' || otpPending) return;
        if (emailInput) emailInput.style.display = 'block';
        if (phoneInput) phoneInput.style.display = 'none';
        if (otpChannelInput) otpChannelInput.value = 'email';
    };

    const setMode = (mode) => {
        authMode = mode;
        otpPending = false;
        registrationContactVerified = false;
        recoveryPending = false;
        const isRegister = mode === 'register';
        if (title) title.textContent = isRegister ? 'Verify Contact' : 'Login';
        if (emailInput) {
            emailInput.placeholder = 'Enter your email';
            emailInput.style.display = isRegister ? 'block' : 'none';
        }
        if (phoneInput) phoneInput.style.display = 'none';
        if (otpChannelInput) otpChannelInput.style.display = 'none';
        if (emailInput) emailInput.required = false;
        if (phoneInput) phoneInput.required = false;
        if (otpChannelInput) otpChannelInput.required = true;
        if (otpInput) {
            otpInput.style.display = 'none';
            otpInput.required = false;
            otpInput.value = '';
        }
        if (usernameInput) {
            usernameInput.style.display = isRegister ? 'none' : 'block';
            usernameInput.required = !isRegister;
        }
        if (passwordInput) {
            passwordInput.style.display = isRegister ? 'none' : 'block';
            passwordInput.required = !isRegister;
        }
        if (newPasswordInput) {
            newPasswordInput.style.display = 'none';
            newPasswordInput.required = false;
            newPasswordInput.value = '';
        }
        if (forgotBtn) forgotBtn.style.display = isRegister ? 'none' : 'block';
        if (loginTab) loginTab.classList.toggle('active', !isRegister);
        if (registerTab) registerTab.classList.toggle('active', isRegister);
        syncRegisterContactFields();
        if (status) {
            status.textContent = '';
            status.className = 'auth-status';
        }
    };

    const setOtpMode = (message) => {
        otpPending = true;
        const isRegister = authMode === 'register';
        if (title) title.textContent = recoveryPending ? 'Recover Account' : isRegister ? 'Verify OTP and Create Password' : 'Enter OTP';
        if (emailInput) emailInput.style.display = 'none';
        if (phoneInput) phoneInput.style.display = 'none';
        if (otpChannelInput) otpChannelInput.style.display = 'none';
        if (emailInput) emailInput.required = false;
        if (phoneInput) phoneInput.required = false;
        if (otpChannelInput) otpChannelInput.required = false;
        if (usernameInput) {
            usernameInput.style.display = isRegister ? 'block' : 'none';
            usernameInput.required = isRegister;
        }
        if (passwordInput) {
            passwordInput.style.display = isRegister ? 'block' : 'none';
            passwordInput.required = isRegister;
        }
        if (newPasswordInput) {
            newPasswordInput.style.display = recoveryPending ? 'block' : 'none';
            newPasswordInput.required = false;
            newPasswordInput.value = '';
        }
        if (otpInput) {
            otpInput.style.display = 'block';
            otpInput.required = true;
            otpInput.value = '';
            otpInput.focus();
        }
        registrationContactVerified = isRegister;
        if (loginTab) loginTab.classList.add('active');
        if (registerTab) registerTab.classList.remove('active');
        setStatus(message || 'Enter the 6-digit OTP.', 'info');
    };

    const setStatus = (message, type = 'info') => {
        if (!status) return;
        status.textContent = message;
        status.className = `auth-status ${type}`;
    };

    const updateAuthUi = (user) => {
        currentUser = user;
        if (authBtn) authBtn.textContent = user ? `Logout ${user.username}` : 'Login';
        if (adminLink) adminLink.style.display = user && user.is_admin ? 'inline-flex' : 'none';
    };

    fetchAPI('/api/auth/me').then((response) => {
        updateAuthUi(response && response.authenticated ? response.user : null);
    });

    if (authBtn) {
        authBtn.addEventListener('click', async (event) => {
            event.preventDefault();
            if (currentUser) {
                await fetch('/api/auth/logout', { method: 'POST' });
                updateAuthUi(null);
                showToast('Logged out', 'info', 1800);
                return;
            }
            pendingRedirect = null;
            if (modal) modal.classList.add('show');
        });
    }

    gatedLinks.forEach((link) => {
        link.addEventListener('click', (event) => {
            const redirectTo = link.getAttribute('data-auth-redirect') || link.getAttribute('href') || '/chat';
            if (currentUser) {
                window.location.href = redirectTo;
                return;
            }
            event.preventDefault();
            pendingRedirect = redirectTo;
            setMode('login');
            if (modal) modal.classList.add('show');
        });
    });

    const query = new URLSearchParams(window.location.search);
    if (query.get('auth') === '1' && modal) {
        pendingRedirect = query.get('next') || '/chat';
        modal.classList.add('show');
    }

    if (closeBtn && modal) {
        closeBtn.addEventListener('click', () => modal.classList.remove('show'));
        modal.addEventListener('click', (event) => {
            if (event.target === modal) modal.classList.remove('show');
        });
    }

    if (loginTab) loginTab.addEventListener('click', () => setMode('login'));
    if (registerTab) registerTab.addEventListener('click', () => setMode('register'));
    if (otpChannelInput) otpChannelInput.addEventListener('change', syncRegisterContactFields);
    if (forgotBtn) {
        forgotBtn.addEventListener('click', () => {
            authMode = 'recovery';
            otpPending = false;
            recoveryPending = false;
            registrationContactVerified = false;
            if (title) title.textContent = 'Recover Account';
            if (emailInput) {
                emailInput.style.display = 'block';
                emailInput.placeholder = 'Registered email or phone';
            }
            if (phoneInput) phoneInput.style.display = 'none';
            if (otpChannelInput) otpChannelInput.style.display = 'none';
            if (usernameInput) usernameInput.style.display = 'none';
            if (passwordInput) passwordInput.style.display = 'none';
            if (newPasswordInput) newPasswordInput.style.display = 'none';
            if (otpInput) otpInput.style.display = 'none';
            if (forgotBtn) forgotBtn.style.display = 'none';
            if (loginTab) loginTab.classList.remove('active');
            if (registerTab) registerTab.classList.remove('active');
            setStatus('Enter your registered email or phone. You can recover username or set a new password.', 'info');
            if (emailInput) emailInput.focus();
        });
    }

    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (submitBtn && submitBtn.disabled) return;

            const payload = otpPending
                ? {
                    otp: otpInput?.value.trim(),
                    username: registrationContactVerified ? usernameInput?.value.trim() : undefined,
                    password: registrationContactVerified ? passwordInput?.value : undefined,
                    new_password: recoveryPending ? newPasswordInput?.value : undefined,
                }
                : {
                    username: usernameInput?.value.trim(),
                    password: passwordInput?.value,
                };
            if (!otpPending && authMode === 'register') {
                payload.email = emailInput?.value.trim();
                payload.phone_number = '';
                payload.otp_channel = 'email';
            }

            if (otpPending && !payload.otp) {
                setStatus('Enter the OTP code.', 'error');
                return;
            }

            if (!otpPending && authMode === 'login' && (!payload.username || !payload.password)) {
                setStatus('Enter username and password.', 'error');
                return;
            }

            if (!otpPending && authMode === 'recovery') {
                payload.identifier = emailInput?.value.trim();
                if (!payload.identifier) {
                    setStatus('Enter your registered email or phone.', 'error');
                    return;
                }
            }

            if (!otpPending && authMode === 'register' && !payload.email && !payload.phone_number) {
                setStatus('Enter your email to receive OTP.', 'error');
                return;
            }

            if (!otpPending && authMode === 'register' && payload.otp_channel === 'email' && !payload.email) {
                setStatus('Enter an email address for email OTP.', 'error');
                return;
            }

            if (!otpPending && authMode === 'register' && payload.otp_channel === 'phone' && !payload.phone_number) {
                setStatus('Enter a phone number with country code for phone OTP.', 'error');
                return;
            }

            if (registrationContactVerified && (!payload.username || !payload.password)) {
                setStatus('Create a username and password.', 'error');
                return;
            }

            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = otpPending ? 'Verifying...' : authMode === 'register' || authMode === 'recovery' ? 'Send OTP' : 'Logging in...';
            }
            setStatus(otpPending ? 'Verifying OTP...' : authMode === 'register' || authMode === 'recovery' ? 'Sending OTP...' : 'Checking your login...', 'info');

            try {
                const endpoint = registrationContactVerified
                    ? '/api/auth/complete-registration'
                    : recoveryPending
                    ? '/api/auth/recovery/complete'
                    : otpPending
                    ? '/api/auth/verify-otp'
                    : authMode === 'recovery'
                    ? '/api/auth/recovery/start'
                    : `/api/auth/${authMode}`;
                const authResponse = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const response = await authResponse.json().catch(() => null);

                if (!otpPending && authResponse.ok && response && response.otp_required) {
                    if (authMode === 'recovery') recoveryPending = true;
                    setOtpMode(response.message);
                    showToast('OTP required', 'info', 1800);
                    return;
                }

                if (authResponse.ok && response && response.success) {
                    if (recoveryPending) {
                        const passwordText = response.password_updated ? ' Password updated.' : '';
                        setStatus(`Your username is ${response.username}.${passwordText}`, 'success');
                        showToast('Recovery complete', 'info', 2200);
                        recoveryPending = false;
                        otpPending = false;
                        return;
                    }
                    updateAuthUi(response.user);
                    setStatus('Success. Opening chat...', 'success');
                    showToast(authMode === 'register' ? 'Account created' : 'Logged in', 'info', 1800);
                    if (pendingRedirect) {
                        window.location.href = pendingRedirect;
                        return;
                    }
                    if (modal) modal.classList.remove('show');
                    await loadChatHistory();
                } else {
                    setStatus(response?.error || 'Authentication failed. Try again.', 'error');
                    showToast(response?.error || 'Authentication failed', 'error', 3500);
                }
            } catch (error) {
                setStatus('Could not reach the server. Make sure Flask is running.', 'error');
                showToast('Could not reach the server', 'error', 3500);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Continue';
                }
            }
        });
    }
}

function setupUploadControls() {
    const fileBtn = document.getElementById('file-upload-btn');
    const imageBtn = document.getElementById('image-upload-btn');
    const fileInput = document.getElementById('file-upload-input');
    const imageInput = document.getElementById('image-upload-input');

    const upload = async (endpoint, fieldName, file) => {
        const formData = new FormData();
        formData.append(fieldName, file);
        formData.append('session_id', getSessionId());
        addMessage(`Uploaded ${file.name}`, 'user');
        showToast('Uploading...', 'info', 1200);

        const response = await fetch(endpoint, { method: 'POST', body: formData });
        const data = await response.json().catch(() => null);
        if (data && data.success) {
            addMessage(data.summary || data.analysis || 'Upload complete.', 'bot');
            showToast('Upload complete', 'info', 1800);
        } else {
            addMessage(data?.error || 'Upload failed.', 'bot');
            showToast('Upload failed', 'error', 3000);
        }
    };

    if (fileBtn && fileInput) {
        fileBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', () => {
            const file = fileInput.files && fileInput.files[0];
            if (file) upload('/api/files/upload', 'file', file);
            fileInput.value = '';
        });
    }

    if (imageBtn && imageInput) {
        imageBtn.addEventListener('click', () => imageInput.click());
        imageInput.addEventListener('change', () => {
            const file = imageInput.files && imageInput.files[0];
            if (file) upload('/api/images/analyze', 'image', file);
            imageInput.value = '';
        });
    }
}

async function setupAdminDashboard() {
    const stats = document.getElementById('admin-stats');
    const users = document.getElementById('admin-users');
    const uploads = document.getElementById('admin-uploads');
    const messages = document.getElementById('admin-messages');
    const refresh = document.getElementById('admin-refresh');
    if (!stats) return;

    const item = (primary, secondary = '') => `<div class="admin-list-item"><strong>${escapeHtml(primary || '')}</strong><span>${escapeHtml(secondary || '')}</span></div>`;

    const load = async () => {
        const data = await fetchAPI('/api/admin/dashboard');
        if (!data || !data.success) {
            showToast('Admin data unavailable. Login as admin first.', 'error', 3500);
            return;
        }

        stats.innerHTML = Object.entries(data.stats).map(([key, value]) => (
            `<div class="admin-stat"><span>${escapeHtml(key)}</span><strong>${value}</strong></div>`
        )).join('');
        users.innerHTML = data.users.map((user) => item(user.username, user.is_admin ? 'Admin' : user.email || 'User')).join('') || item('No users yet');
        uploads.innerHTML = data.uploads.map((uploadItem) => item(uploadItem.filename, `${uploadItem.file_type} · ${uploadItem.size_bytes} bytes`)).join('') || item('No uploads yet');
        messages.innerHTML = data.messages.map((message) => item(message.user, message.bot)).join('') || item('No messages yet');
    };

    if (refresh) refresh.addEventListener('click', load);
    await load();
}

/**
 * Update Mini Map
 */
function updateMiniMap(location) {
    const frame = document.getElementById('mini-map-frame');
    if (!frame || !location || !location.coords) return;

    const lat = Number(location.coords.lat);
    const lng = Number(location.coords.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) return;

    const delta = 0.12;
    const bbox = [
        lng - delta,
        lat - delta,
        lng + delta,
        lat + delta,
    ].join('%2C');

    frame.src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${lat}%2C${lng}`;
}

/**
 * Update Geolocation Interface
 */
function updateGeolocationInterface(location, options = {}) {
    const cityElement = document.getElementById('geo-city');
    const countryElement = document.getElementById('geo-country');
    const latElement = document.getElementById('geo-lat');
    const lngElement = document.getElementById('geo-lng');
    const statusElement = document.getElementById('geo-status');

    if (!cityElement || !countryElement || !latElement || !lngElement || !statusElement) return;

    const coords = location && location.coords ? location.coords : {};
    const lat = Number(coords.lat);
    const lng = Number(coords.lng);
    const hasCoords = Number.isFinite(lat) && Number.isFinite(lng) && (lat !== 0 || lng !== 0);

    if (location) {
        cityElement.textContent = location.city || options.city || (hasCoords ? 'Current location' : 'Unknown');
        countryElement.textContent = location.country || options.country || location.timezone || 'Local device';
    }

    if (hasCoords) {
        latElement.textContent = lat.toFixed(5);
        lngElement.textContent = lng.toFixed(5);
    }

    statusElement.textContent = options.status || (hasCoords ? 'Location locked on map' : 'Location unavailable');
}

function setCurrentBrowserLocation(location) {
    if (!location || !location.coords) return;

    const lat = Number(location.coords.lat);
    const lng = Number(location.coords.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) return;

    CURRENT_BROWSER_LOCATION = {
        ...location,
        coords: { lat, lng },
        capturedAt: Date.now(),
    };

    try {
        localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(CURRENT_BROWSER_LOCATION));
    } catch (error) {
        console.warn('Could not cache browser location:', error);
    }
}

function loadCachedBrowserLocation() {
    if (CURRENT_BROWSER_LOCATION) return CURRENT_BROWSER_LOCATION;

    try {
        const cached = JSON.parse(localStorage.getItem(LOCATION_STORAGE_KEY) || 'null');
        if (!cached || !cached.capturedAt) return null;
        if (Date.now() - cached.capturedAt > 10 * 60 * 1000) return null;
        setCurrentBrowserLocation(cached);
        return CURRENT_BROWSER_LOCATION;
    } catch (error) {
        return null;
    }
}

async function detectBrowserLocation(options = {}) {
    if (CURRENT_BROWSER_LOCATION || loadCachedBrowserLocation()) return CURRENT_BROWSER_LOCATION;
    if (BROWSER_LOCATION_PROMISE) return BROWSER_LOCATION_PROMISE;

    BROWSER_LOCATION_PROMISE = new Promise((resolve) => {
        if (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(window.location.hostname)) {
            updateGeolocationInterface(null, {
                status: 'Location needs HTTPS on mobile browsers',
            });
            resolve(null);
            return;
        }

        if (!navigator.geolocation) {
            updateGeolocationInterface(null, {
                status: 'Browser location is not supported',
            });
            resolve(null);
            return;
        }

        updateGeolocationInterface(null, {
            status: options.silent ? 'Checking location' : 'Requesting browser location',
        });

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                const resolvedPlace = await resolveLocationNameFromCoords(lat, lng);
                const location = {
                    city: resolvedPlace?.city || 'Current location',
                    country: resolvedPlace?.country || 'Local device',
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
                    coords: { lat, lng },
                };

                updateMiniMap(location);
                setCurrentBrowserLocation(location);
                updateGeolocationInterface(location, {
                    status: resolvedPlace
                        ? `Location resolved, accuracy about ${Math.round(position.coords.accuracy)} m`
                        : `Coordinates active, accuracy about ${Math.round(position.coords.accuracy)} m`,
                });
                resolve(CURRENT_BROWSER_LOCATION);
            },
            (error) => {
                console.warn('Location permission unavailable:', error.message);
                updateGeolocationInterface(null, {
                    status: error.code === 1
                        ? 'Location permission denied in browser settings'
                        : 'Browser location unavailable, trying network location',
                });
                resolve(null);
            },
            {
                enableHighAccuracy: true,
                timeout: options.timeout || 10000,
                maximumAge: 300000,
            }
        );
    }).finally(() => {
        BROWSER_LOCATION_PROMISE = null;
    });

    return BROWSER_LOCATION_PROMISE;
}

async function fetchServerLocationForMap(statusPrefix = 'Using network location') {
    const data = await fetchAPI('/api/location');
    if (!data || !data.success || !data.location) return false;

    const location = {
        city: data.location.city,
        country: data.location.country,
        timezone: data.timezone || data.location.timezone,
        coords: {
            lat: data.location.latitude,
            lng: data.location.longitude,
        },
    };

    updateMiniMap(location);
    setCurrentBrowserLocation(location);
    updateGeolocationInterface(location, {
        status: `${statusPrefix}${location.timezone ? ` (${location.timezone})` : ''}`,
    });

    return true;
}

async function resolveLocationNameFromCoords(lat, lng) {
    try {
        const params = new URLSearchParams({
            latitude: lat,
            longitude: lng,
            localityLanguage: 'en',
        });
        const response = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?${params.toString()}`);

        if (!response.ok) return null;

        const data = await response.json();
        const city = data.city || data.locality || data.principalSubdivision || data.localityInfo?.administrative?.[0]?.name;
        const country = data.countryName || data.principalSubdivision || 'Current location';

        if (!city && !country) return null;

        return {
            city: city || 'Current location',
            country,
        };
    } catch (error) {
        console.warn('Reverse geocode failed:', error);
        return null;
    }
}

/**
 * Initialize Mini Map With Browser Location
 */
async function initCurrentLocationMap() {
    const frame = document.getElementById('mini-map-frame');
    const refreshBtn = document.getElementById('geo-refresh-btn');
    if (!frame) return;

    const setLoading = (isLoading) => {
        if (!refreshBtn) return;
        refreshBtn.classList.toggle('loading', isLoading);
        refreshBtn.disabled = isLoading;
    };

    const refreshLocation = async () => {
        setLoading(true);
        const hasBrowserLocation = await detectBrowserLocation({ timeout: 10000 });
        if (!hasBrowserLocation) {
            await fetchServerLocationForMap();
        }
        setLoading(false);
    };

    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshLocation);
    }

    await refreshLocation();
}
/**
 * Add Chat Message
 */
function addMessage(text, sender) {
    const container = document.getElementById('chat-messages-3d');
    if (!container) return;
    
    // Remove welcome message if exists
    const welcome = container.querySelector('.chat-welcome-3d');
    if (welcome && sender === 'user') welcome.remove();
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}-message`;
    const wrapper = document.createElement('div');
     wrapper.className = 'message-content';

    const p = document.createElement('p');  
    p.textContent = text;

     wrapper.appendChild(p);
     messageDiv.appendChild(wrapper);
     container.appendChild(messageDiv);
    
    if (CONFIG_3D.settings.autoScroll) {
        container.scrollTop = container.scrollHeight;
    }
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Trigger 3D Effect
 */
function trigger3DEffect(effect) {
    console.log('Triggering 3D effect:', effect);
    
    switch(effect) {
        case 'morph':
            runMorphEffect();
            break;
        case 'rotate':
            gsap.to(CONFIG_3D.morphingGeometry.rotation, {
                y: '+=2',
                duration: 1.5,
                ease: 'power2.out',
            });
            break;
        case 'scale':
            gsap.to(CONFIG_3D.morphingGeometry.scale, {
                x: 1.2,
                y: 1.2,
                z: 1.2,
                duration: 0.5,
                yoyo: true,
                repeat: 1,
            });
            break;
    }
}

/**
 * Setup Settings Modal
 */
function setupSettingsModal() {
    const settingsBtn = document.getElementById('settings-btn');
    const modal = document.getElementById('settings-modal');
    const modalClose = document.getElementById('modal-close');
    
    if (!settingsBtn || !modal) return;
    
    settingsBtn.addEventListener('click', () => {
        modal.classList.add('show');
    });
    
    if (modalClose) {
        modalClose.addEventListener('click', () => {
            modal.classList.remove('show');
        });
    }
    
    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('show');
    });
    
    // Settings toggles
    const particleToggle = document.getElementById('particle-toggle');
    const morphToggle = document.getElementById('morph-toggle');
    const autoScrollToggle = document.getElementById('auto-scroll-toggle');
    const geometrySelect = document.getElementById('geometry-select');
    
    if (particleToggle) {
        particleToggle.addEventListener('change', (e) => {
            CONFIG_3D.settings.particlesEnabled = e.target.checked;
            if (CONFIG_3D.particles) {
                CONFIG_3D.particles.visible = e.target.checked;
            }
        });
    }
    
    if (morphToggle) {
        morphToggle.checked = CONFIG_3D.settings.morphingEnabled;
        morphToggle.addEventListener('change', (e) => {
            CONFIG_3D.settings.morphingEnabled = e.target.checked;
            CONFIG_3D.morphOverrideUntil = 0;

            if (CONFIG_3D.morphingGeometry && CONFIG_3D.morphingGeometry.material.uniforms) {
                CONFIG_3D.morphingGeometry.visible = true;
                CONFIG_3D.morphingGeometry.material.uniforms.uMorphFactor.value = e.target.checked ? 0.7 : 0;
            }

            setAvatarStatus(e.target.checked ? 'Morphing on' : 'Morphing off');
            showToast(e.target.checked ? 'Morphing enabled' : 'Morphing disabled', 'info', 1400);
        });
    }
    
    if (autoScrollToggle) {
        autoScrollToggle.addEventListener('change', (e) => {
            CONFIG_3D.settings.autoScroll = e.target.checked;
        });
    }
    
    if (geometrySelect) {
        geometrySelect.value = CONFIG_3D.settings.geometry;
        geometrySelect.addEventListener('change', (e) => {
            replaceMorphingGeometry(e.target.value);
        });
    }
}

/**
 * Setup Avatar Controls
 */
function setupAvatarControls() {
    const morphBtn = document.getElementById('morph-btn');
    const rotateBtn = document.getElementById('rotate-btn');
    const emitBtn = document.getElementById('emit-btn');
    
    if (morphBtn) {
        morphBtn.addEventListener('click', () => {
            runMorphEffect();
        });
    }
    
    if (rotateBtn) {
        rotateBtn.addEventListener('click', () => {
            if (CONFIG_3D.morphingGeometry) {
                gsap.to(CONFIG_3D.morphingGeometry.rotation, {
                    y: '+=2',
                    duration: 1.5,
                    ease: 'power2.out',
                });
            }
        });
    }
    
    if (emitBtn) {
        emitBtn.addEventListener('click', () => {
            if (CONFIG_3D.particles) {
                gsap.to(CONFIG_3D.particles.material.uniforms.uTime, {
                    value: Math.random() * 10,
                    duration: 0.5,
                });
            }
        });
    }
}

/**
 * Setup Suggestion Buttons
 */
function setupSuggestions() {
    const suggestionBtns = document.querySelectorAll('.suggestion-btn');
    const input = document.getElementById('chat-input-3d');
    
    if (!input) return;
    
    suggestionBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const question = btn.getAttribute('data-question');
            input.value = question;
            input.focus();
            
            // Trigger send
            const sendBtn = document.getElementById('send-btn-3d');
            if (sendBtn) sendBtn.click();
        });
    });
}

/**
 * Setup CTA Buttons
 */
function setupCTAButtons() {
    const exploreBtn = document.getElementById('explore-btn');
    
    if (exploreBtn) {
        exploreBtn.addEventListener('click', () => {
            const featuresSection = document.querySelector('.features-section-3d');
            if (featuresSection) {
                featuresSection.scrollIntoView({ behavior: 'smooth' });
            }
        });
    }
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const hideLoadingOverlay = () => {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            setTimeout(() => {
                loadingOverlay.classList.add('hide');
            }, 500);
        }
    };

    try {
        // Setup gradient background
        initGradientCanvas();
        
        // Setup UI
        setupThemeToggle();
        setupResponsiveNav();
        setupCTAButtons();
        
        // Determine page type
        const isHomePage = document.querySelector('.landing-page');
        const isChatPage = document.querySelector('.chat-page');
        const isAboutPage = document.querySelector('.about-page');
        const isAdminPage = document.querySelector('.admin-page');
        
        if (isHomePage) {
            setupAuthControls();
            // Initialize 3D scene
            if (init3DScene('three-canvas')) {
                console.log('Home page 3D scene initialized');
            }
        } else if (isChatPage) {
            // Initialize chat 3D scene
            if (init3DScene('three-canvas-chat')) {
                console.log('Chat page 3D scene initialized');
                initCurrentLocationMap();
                setupChatInterface();
                setupAuthControls();
                setupUploadControls();
                setupSettingsModal();
                setupAvatarControls();
                setupSuggestions();
                loadChatHistory();
            } else {
                setupChatInterface();
                setupAuthControls();
                setupUploadControls();
                setupSettingsModal();
                setupSuggestions();
                loadChatHistory();
            }
        } else if (isAdminPage) {
            setupAdminDashboard();
        } else if (isAboutPage) {
            // Initialize about 3D scene
            if (init3DScene('three-canvas-about')) {
                console.log('About page 3D scene initialized');
            }
        }
    } catch (error) {
        console.error('Page initialization failed:', error);
        showToast('3D initialization failed. The page is still usable.', 'error', 5000);
    } finally {
        hideLoadingOverlay();
    }
});

// ============================================================================
// SCROLL ANIMATIONS WITH GSAP
// ============================================================================

if (typeof gsap !== 'undefined' && typeof ScrollTrigger !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);
    
    document.addEventListener('DOMContentLoaded', () => {
        // Animate sections on scroll
        const sections = document.querySelectorAll('.about-section-3d, .features-section-3d, .tech-section-3d');
        
        sections.forEach((section, index) => {
            gsap.from(section, {
                scrollTrigger: {
                    trigger: section,
                    start: 'top 80%',
                },
                opacity: 0,
                y: 50,
                duration: 0.8,
                delay: index * 0.1,
            });
        });
    });
}

// ============================================================================
// END OF SCRIPT
// ============================================================================
