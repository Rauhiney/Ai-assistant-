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
 * Initialize Gradient Canvas Background
 */
function initGradientCanvas() {
    const canvas = document.getElementById('gradient-canvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    
    // Draw animated gradient
    const drawGradient = () => {
        const time = Date.now() * 0.0001;
        
        const gradient = ctx.createLinearGradient(
            Math.sin(time) * window.innerWidth,
            Math.cos(time) * window.innerHeight,
            Math.cos(time) * window.innerWidth,
            Math.sin(time) * window.innerHeight
        );
        
        gradient.addColorStop(0, 'rgba(74, 158, 255, 0.1)');
        gradient.addColorStop(0.5, 'rgba(255, 107, 157, 0.05)');
        gradient.addColorStop(1, 'rgba(0, 255, 136, 0.05)');
        
        ctx.fillStyle = gradient;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        requestAnimationFrame(drawGradient);
    };
    
    drawGradient();
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
        
        if (!response.ok) throw new Error(`API Error: ${response.status}`);
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
            gl_PointSize = size * (1.0 - life) * 10.0;
        }
    `;
    
    const fragmentShader = `
        varying float vLife;
        varying vec3 vColor;
        
        void main() {
            // Circle shape
            vec2 circCoord = 2.0 * gl_PointCoord - 1.0;
            float dist = dot(circCoord, circCoord);
            
            if (dist > 1.0) discard;
            
            float alpha = (1.0 - dist) * vLife;
            gl_FragColor = vec4(vColor, alpha);
        }
    `;
    
    return new THREE.ShaderMaterial({
        uniforms: {
            uTime: { value: 0 },
        },
        vertexShader,
        fragmentShader,
        transparent: true,
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
    const sceneBackground = isLightTheme ? 0xf7fbff : 0x0a0e27;

    // Scene setup
    CONFIG_3D.scene = new THREE.Scene();
    CONFIG_3D.scene.background = new THREE.Color(sceneBackground);
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
    
    // Head
    const headGeometry = new THREE.IcosahedronGeometry(0.5, 4);
    const headMaterial = new THREE.MeshStandardMaterial({
        color: 0x4a9eff,
        metalness: 0.3,
        roughness: 0.4,
        emissive: 0x1a4d99,
        emissiveIntensity: 0.15,
    });
    const head = new THREE.Mesh(headGeometry, headMaterial);
    head.position.y = 1;
    group.add(head);
    
    // Eyes
    const eyeGeometry = new THREE.SphereGeometry(0.1, 16, 16);
    const eyeMaterial = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        emissive: 0x00ff88,
        emissiveIntensity: 0.8,
    });
    
    const leftEye = new THREE.Mesh(eyeGeometry, eyeMaterial);
    leftEye.position.set(-0.15, 1.15, 0.4);
    group.add(leftEye);
    
    const rightEye = new THREE.Mesh(eyeGeometry, eyeMaterial);
    rightEye.position.set(0.15, 1.15, 0.4);
    group.add(rightEye);
    
    // Body
    const bodyGeometry = new THREE.CylinderGeometry(0.3, 0.4, 1, 32);
    const bodyMaterial = new THREE.MeshStandardMaterial({
        color: 0x2a5a9f,
        metalness: 0.3,
        roughness: 0.5,
    });
    const body = new THREE.Mesh(bodyGeometry, bodyMaterial);
    body.position.y = -0.2;
    group.add(body);
    
    CONFIG_3D.avatar = group;
    CONFIG_3D.scene.add(group);
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
            const backgroundColor = isLight ? 0xf7fbff : 0x0a0e27;
            CONFIG_3D.scene.background = new THREE.Color(backgroundColor);
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
            const response = await fetchAPI('/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    message,
                    session_id: getSessionId(),
                }),
            });
            
            if (response && response.success) {
                addMessage(response.response, 'bot');
                updateMiniMap(response.location);
                
                // Trigger 3D effect
                if (response['3d_effect']) {
                    trigger3DEffect(response['3d_effect']);
                }
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
 * Initialize Mini Map With Browser Location
 */
function initCurrentLocationMap() {
    const frame = document.getElementById('mini-map-frame');
    if (!frame || !navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
        (position) => {
            updateMiniMap({
                coords: {
                    lat: position.coords.latitude,
                    lng: position.coords.longitude,
                },
            });
        },
        (error) => {
            console.warn('Location permission unavailable:', error.message);
        },
        {
            enableHighAccuracy: false,
            timeout: 3000,
            maximumAge: 300000,
        }
    );
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
        
        if (isHomePage) {
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
                setupSettingsModal();
                setupAvatarControls();
                setupSuggestions();
            } else {
                setupChatInterface();
                setupSettingsModal();
                setupSuggestions();
            }
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
