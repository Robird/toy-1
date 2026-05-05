const canvas = document.getElementById("gameCanvas");
const context = canvas.getContext("2d");
const stageLabel = document.getElementById("stageLabel");
const massLabel = document.getElementById("massLabel");
const resetButton = document.getElementById("resetButton");

const stageDefs = [
  { threshold: 1, name: "小石头", core: "#c8d1df", rim: "#eef6ff", halo: "rgba(152, 217, 255, 0.28)" },
  { threshold: 20, name: "热核星胚", core: "#ffd166", rim: "#fff1b4", halo: "rgba(255, 209, 102, 0.28)" },
  { threshold: 60, name: "蓝白恒星", core: "#7ee7ff", rim: "#ffffff", halo: "rgba(126, 231, 255, 0.32)" },
  { threshold: 140, name: "小黑洞", core: "#0d1024", rim: "#7f8fff", halo: "rgba(127, 143, 255, 0.32)" }
];

const orbitColors = ["#ffd166", "#7ee7ff", "#ff8fab", "#b8f2e6", "#c8b6ff"];
const entityTiers = [
  { radius: 10, value: 1, count: 38, color: "#ffd166" },
  { radius: 16, value: 3, count: 24, color: "#ff8fab" },
  { radius: 26, value: 8, count: 18, color: "#7ee7ff" },
  { radius: 44, value: 18, count: 12, color: "#c8b6ff" },
  { radius: 72, value: 40, count: 8, color: "#b8f2e6" },
  { radius: 116, value: 80, count: 5, color: "#ffffff" }
];

const state = {
  width: 0,
  height: 0,
  dpr: Math.max(1, Math.min(window.devicePixelRatio || 1, 2)),
  playerWorldRadius: 24,
  playerScreenRadius: 30,
  playerMass: 1,
  worldScale: 1,
  worldX: 0,
  worldY: 0,
  velocityX: 0,
  velocityY: 0,
  pulse: 0,
  stageIndex: 0,
  entities: [],
  stars: [],
  pointer: { active: false, x: 0, y: 0 },
  lastTime: 0
};

function resizeCanvas() {
  state.width = window.innerWidth;
  state.height = window.innerHeight;
  state.dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
  canvas.width = Math.floor(state.width * state.dpr);
  canvas.height = Math.floor(state.height * state.dpr);
  canvas.style.width = `${state.width}px`;
  canvas.style.height = `${state.height}px`;
  context.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
  buildStarfield();
}

function buildStarfield() {
  const starCount = Math.max(120, Math.round((state.width * state.height) / 9000));
  state.stars = Array.from({ length: starCount }, () => ({
    x: Math.random() * state.width,
    y: Math.random() * state.height,
    radius: Math.random() * 1.7 + 0.3,
    alpha: Math.random() * 0.6 + 0.2,
    drift: Math.random() * 0.2 + 0.05
  }));
}

function resetGame() {
  state.playerMass = 1;
  state.playerWorldRadius = 24;
  state.worldScale = 1;
  state.worldX = 0;
  state.worldY = 0;
  state.velocityX = 0;
  state.velocityY = 0;
  state.pulse = 0;
  state.entities = [];
  updateStage();
  refillEntities(true);
}

function updateStage() {
  let index = 0;
  for (let i = 0; i < stageDefs.length; i += 1) {
    if (state.playerMass >= stageDefs[i].threshold) {
      index = i;
    }
  }
  state.stageIndex = index;
  stageLabel.textContent = stageDefs[index].name;
  massLabel.textContent = `质量 ${Math.floor(state.playerMass)}`;
}

function getViewRadiusWorld() {
  const screenRadius = Math.hypot(state.width, state.height) * 0.5;
  return screenRadius / state.worldScale;
}

function spawnEntity(tier, minRadiusWorld, maxRadiusWorld) {
  const angle = Math.random() * Math.PI * 2;
  const distance = minRadiusWorld + Math.random() * (maxRadiusWorld - minRadiusWorld);
  return {
    x: state.worldX + Math.cos(angle) * distance,
    y: state.worldY + Math.sin(angle) * distance,
    worldRadius: tier.radius,
    massValue: tier.value,
    color: tier.color,
    wobble: Math.random() * Math.PI * 2,
    wobbleSpeed: Math.random() * 1.2 + 0.4,
    orbitDot: orbitColors[Math.floor(Math.random() * orbitColors.length)]
  };
}

function refillEntities(force = false) {
  const viewRadius = getViewRadiusWorld();
  const spawnMin = force ? viewRadius * 0.35 : viewRadius * 0.85;
  const spawnMax = viewRadius * 2.3;

  for (const tier of entityTiers) {
    let count = 0;
    for (const entity of state.entities) {
      if (entity.worldRadius === tier.radius) {
        const dx = entity.x - state.worldX;
        const dy = entity.y - state.worldY;
        const distance = Math.hypot(dx, dy);
        if (distance < spawnMax) {
          count += 1;
        }
      }
    }

    while (count < tier.count) {
      state.entities.push(spawnEntity(tier, spawnMin, spawnMax));
      count += 1;
    }
  }
}

function screenRadiusFor(entity) {
  return entity.worldRadius * state.worldScale;
}

function handleInput(dt) {
  const centerX = state.width * 0.5;
  const centerY = state.height * 0.5;

  let intentX = 0;
  let intentY = 0;

  if (state.pointer.active) {
    intentX = (state.pointer.x - centerX) / Math.max(80, state.width * 0.18);
    intentY = (state.pointer.y - centerY) / Math.max(80, state.height * 0.18);
  }

  const magnitude = Math.hypot(intentX, intentY);
  if (magnitude > 1) {
    intentX /= magnitude;
    intentY /= magnitude;
  }

  const speed = 240 / Math.max(0.55, Math.pow(state.playerMass, 0.12));
  const targetVelocityX = intentX * speed;
  const targetVelocityY = intentY * speed;
  const smoothing = 1 - Math.exp(-dt * 8);

  state.velocityX += (targetVelocityX - state.velocityX) * smoothing;
  state.velocityY += (targetVelocityY - state.velocityY) * smoothing;
  state.worldX += state.velocityX * dt;
  state.worldY += state.velocityY * dt;
}

function absorbEntity(entity) {
  state.playerMass += entity.massValue;
  state.pulse = 1;
  state.worldScale = Math.pow(state.playerMass, -0.22);
  updateStage();
}

function updateEntities(dt) {
  const next = [];
  const cullRadius = getViewRadiusWorld() * 2.7;
  const playerCenterX = state.width * 0.5;
  const playerCenterY = state.height * 0.5;
  const playerRadius = state.playerScreenRadius;
  const absorbLimit = playerRadius * 0.98;

  for (const entity of state.entities) {
    entity.wobble += entity.wobbleSpeed * dt;

    const dx = entity.x - state.worldX;
    const dy = entity.y - state.worldY;
    const distanceWorld = Math.hypot(dx, dy);
    if (distanceWorld > cullRadius) {
      continue;
    }

    const screenX = playerCenterX + dx * state.worldScale;
    const screenY = playerCenterY + dy * state.worldScale;
    const renderRadius = screenRadiusFor(entity);

    if (renderRadius < 1.2) {
      continue;
    }

    const screenDistance = Math.hypot(screenX - playerCenterX, screenY - playerCenterY);

    if (renderRadius <= absorbLimit && screenDistance <= playerRadius + renderRadius * 0.8) {
      absorbEntity(entity);
      continue;
    }

    next.push(entity);
  }

  state.entities = next;
  refillEntities();
}

function update(dt) {
  handleInput(dt);
  updateEntities(dt);
  state.pulse = Math.max(0, state.pulse - dt * 2.2);
}

function drawBackdrop(time) {
  const gradient = context.createRadialGradient(
    state.width * 0.5,
    state.height * 0.5,
    80,
    state.width * 0.5,
    state.height * 0.5,
    Math.max(state.width, state.height) * 0.65
  );
  gradient.addColorStop(0, "rgba(36, 62, 120, 0.32)");
  gradient.addColorStop(1, "rgba(2, 5, 18, 0.96)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, state.width, state.height);

  for (const star of state.stars) {
    const twinkle = Math.sin(time * star.drift + star.x * 0.013) * 0.18 + star.alpha;
    context.globalAlpha = Math.max(0.08, twinkle);
    context.fillStyle = "#ffffff";
    context.beginPath();
    context.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
    context.fill();
  }
  context.globalAlpha = 1;
}

function drawEntity(entity) {
  const dx = entity.x - state.worldX;
  const dy = entity.y - state.worldY;
  const screenX = state.width * 0.5 + dx * state.worldScale;
  const screenY = state.height * 0.5 + dy * state.worldScale;
  const renderRadius = screenRadiusFor(entity);

  if (
    renderRadius < 1.4 ||
    screenX < -renderRadius ||
    screenX > state.width + renderRadius ||
    screenY < -renderRadius ||
    screenY > state.height + renderRadius
  ) {
    return;
  }

  const bob = Math.sin(entity.wobble) * Math.max(0.8, renderRadius * 0.04);
  const x = screenX;
  const y = screenY + bob;
  const halo = context.createRadialGradient(x, y, renderRadius * 0.15, x, y, renderRadius * 1.3);
  halo.addColorStop(0, `${entity.color}f2`);
  halo.addColorStop(1, `${entity.color}00`);

  context.fillStyle = halo;
  context.beginPath();
  context.arc(x, y, renderRadius * 1.35, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = entity.color;
  context.beginPath();
  context.arc(x, y, renderRadius, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = "rgba(255, 255, 255, 0.8)";
  context.beginPath();
  context.arc(x - renderRadius * 0.28, y - renderRadius * 0.25, renderRadius * 0.25, 0, Math.PI * 2);
  context.fill();

  if (renderRadius > 18) {
    context.fillStyle = entity.orbitDot;
    context.beginPath();
    context.arc(
      x + Math.cos(entity.wobble * 1.7) * renderRadius * 1.45,
      y + Math.sin(entity.wobble * 1.7) * renderRadius * 0.55,
      Math.max(2, renderRadius * 0.16),
      0,
      Math.PI * 2
    );
    context.fill();
  }
}

function drawPlayer() {
  const stage = stageDefs[state.stageIndex];
  const x = state.width * 0.5;
  const y = state.height * 0.5;
  const pulseScale = 1 + state.pulse * 0.16;
  const radius = state.playerScreenRadius * pulseScale;

  const halo = context.createRadialGradient(x, y, radius * 0.35, x, y, radius * 2.4);
  halo.addColorStop(0, stage.halo);
  halo.addColorStop(1, "rgba(0, 0, 0, 0)");
  context.fillStyle = halo;
  context.beginPath();
  context.arc(x, y, radius * 2.6, 0, Math.PI * 2);
  context.fill();

  const core = context.createRadialGradient(x - radius * 0.2, y - radius * 0.25, radius * 0.18, x, y, radius);
  core.addColorStop(0, stage.rim);
  core.addColorStop(1, stage.core);
  context.fillStyle = core;
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fill();

  if (state.stageIndex >= 3) {
    context.strokeStyle = "rgba(126, 150, 255, 0.92)";
    context.lineWidth = 4;
    context.beginPath();
    context.ellipse(x, y, radius * 1.7, radius * 0.74, performance.now() * 0.001, 0, Math.PI * 2);
    context.stroke();
  }

  context.fillStyle = "rgba(255, 255, 255, 0.92)";
  context.beginPath();
  context.arc(x - radius * 0.28, y - radius * 0.12, radius * 0.16, 0, Math.PI * 2);
  context.arc(x + radius * 0.22, y - radius * 0.18, radius * 0.12, 0, Math.PI * 2);
  context.fill();
}

function drawReachRing() {
  context.strokeStyle = "rgba(190, 226, 255, 0.18)";
  context.lineWidth = 1.5;
  context.setLineDash([8, 10]);
  context.beginPath();
  context.arc(state.width * 0.5, state.height * 0.5, state.playerScreenRadius * 1.9, 0, Math.PI * 2);
  context.stroke();
  context.setLineDash([]);
}

function render(time) {
  drawBackdrop(time * 0.001);
  for (const entity of state.entities) {
    drawEntity(entity);
  }
  drawReachRing();
  drawPlayer();
}

function tick(timestamp) {
  if (!state.lastTime) {
    state.lastTime = timestamp;
  }
  const dt = Math.min(0.033, (timestamp - state.lastTime) / 1000);
  state.lastTime = timestamp;
  update(dt);
  render(timestamp);
  window.requestAnimationFrame(tick);
}

function updatePointerPosition(event) {
  const rect = canvas.getBoundingClientRect();
  state.pointer.x = event.clientX - rect.left;
  state.pointer.y = event.clientY - rect.top;
}

canvas.addEventListener("pointerdown", (event) => {
  state.pointer.active = true;
  updatePointerPosition(event);
});

canvas.addEventListener("pointermove", (event) => {
  updatePointerPosition(event);
  if (event.buttons > 0 || event.pointerType === "mouse") {
    state.pointer.active = true;
  }
});

canvas.addEventListener("pointerup", () => {
  state.pointer.active = false;
});

canvas.addEventListener("pointerleave", () => {
  state.pointer.active = false;
});

resetButton.addEventListener("click", resetGame);
window.addEventListener("resize", resizeCanvas);

resizeCanvas();
resetGame();
window.requestAnimationFrame(tick);