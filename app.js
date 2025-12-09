// ==========================
// CONFIG
// ==========================
const MAX_PLAYERS = 16; // ปรับได้
const COURT_SIZE = 4;   // doubles = 4 คนต่อรอบ

// ==========================
// STATE หลัก
// ==========================
let players = []; // { id, name, gamesPlayed, lastPlayedRound }
let nextId = 1;

let roundNumber = 0;
let lastRoundPlayingIds = [];    // รอบที่แล้วใครได้เล่นบ้าง
let pairCount = new Map();       // key: "id1-id2" -> นับกี่ครั้งแล้ว

// ==========================
// DOM
// ==========================
const nameInput    = document.getElementById('player-name');
const addBtn       = document.getElementById('add-player-btn');
const playersList  = document.getElementById('players-list');
const nextRoundBtn = document.getElementById('next-round-btn');
const roundInfoDiv = document.getElementById('round-info');
const pairInfoDiv  = document.getElementById('pair-info');

// ==========================
// Helper: pair key เช่น "1-3"
// ==========================
function pairKey(id1, id2) {
  return id1 < id2 ? `${id1}-${id2}` : `${id2}-${id1}`;
}

// ==========================
// เพิ่มผู้เล่น + Enter เพื่อเพิ่ม
// ==========================
nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    addBtn.click();
  }
});

addBtn.addEventListener('click', () => {
  const name = nameInput.value.trim();
  if (!name) return;

  if (players.length >= MAX_PLAYERS) {
    alert(`ตัวอย่างนี้กำหนดไว้สูงสุด ${MAX_PLAYERS} คน (เปลี่ยนค่า MAX_PLAYERS ในโค้ดได้)`);
    return;
  }

  players.push({
    id: nextId++,
    name,
    gamesPlayed: 0,
    lastPlayedRound: 0
  });

  nameInput.value = '';
  renderPlayers();
});

// ==========================
// แสดงรายชื่อ + สถิติ
// ==========================
function renderPlayers() {
  playersList.innerHTML = '';
  players.forEach(p => {
    const li = document.createElement('li');

    const nameSpan = document.createElement('span');
    nameSpan.className = 'player-name';
    nameSpan.textContent = p.name;

    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = `เล่นแล้ว ${p.gamesPlayed} เกม`;

    li.appendChild(nameSpan);
    li.appendChild(badge);
    playersList.appendChild(li);
  });
}

// ==========================
// ปุ่ม: สร้างรอบถัดไป
// ==========================
nextRoundBtn.addEventListener('click', () => {
  if (players.length < COURT_SIZE) {
    alert(`ต้องมีอย่างน้อย ${COURT_SIZE} คนขึ้นไปถึงจะจัดรอบได้`);
    return;
  }

  const result = createNextRound();
  if (!result) {
    alert('ไม่สามารถสร้างรอบได้ ลองเช็คจำนวนผู้เล่นอีกครั้ง');
    return;
  }

  const { selectedPlayers, pairs } = result;

  roundNumber++;
  const currentRound = roundNumber;

  // อัปเดต gamesPlayed / lastPlayedRound / pairCount
  selectedPlayers.forEach(p => {
    const real = players.find(x => x.id === p.id);
    if (real) {
      real.gamesPlayed += 1;
      real.lastPlayedRound = currentRound;
    }
  });

  pairs.forEach(([a, b]) => {
    const key = pairKey(a.id, b.id);
    const old = pairCount.get(key) || 0;
    pairCount.set(key, old + 1);
  });

  lastRoundPlayingIds = selectedPlayers.map(p => p.id);

  renderRound(currentRound, selectedPlayers, pairs);
  renderPlayers();
});

// ==========================
// สร้างรอบใหม่:
//   1) ต้องมี "คนที่นั่งรอบที่แล้ว" อย่างน้อยครึ่งหนึ่งของ 4 คน
//   2) เลือกคู่ที่ซ้ำกันน้อยที่สุด
//   3) ดูคนที่รอนาน / เล่นน้อย
// ==========================
function createNextRound() {
  const currentRound = roundNumber + 1;
  const allPlayers = [...players];
  const allIds = allPlayers.map(p => p.id);

  const lastSet = new Set(lastRoundPlayingIds);
  const satIds = allPlayers
    .map(p => p.id)
    .filter(id => !lastSet.has(id));
  const totalSat = satIds.length;
  const satSet = new Set(satIds);

  // ต้องการให้มีคนที่นั่งรอบที่แล้วอย่างน้อยครึ่งหนึ่งของ COURT_SIZE
  const minSatNeeded = totalSat > 0
    ? Math.min(Math.floor(COURT_SIZE / 2), totalSat)
    : 0;

  let bestOption = null;
  const combos = combinations(allIds, COURT_SIZE);

  combos.forEach(comboIds => {
    const groupPlayers = comboIds.map(id => allPlayers.find(p => p.id === id));

    // นับว่ากลุ่มนี้มี "คนที่นั่งรอบที่แล้ว" กี่คน
    const satInGroup = groupPlayers.filter(p => satSet.has(p.id)).length;

    // ถ้ามีคนที่นั่งรอบที่แล้วอยู่ แต่กลุ่มนี้เลือกมาน้อยกว่าที่กำหนด → ข้ามเลย
    if (totalSat > 0 && satInGroup < minSatNeeded) {
      return;
    }

    // เลือกวิธีจับคู่ที่ดีที่สุดในกลุ่ม 4 คนนี้
    const pairingResult = selectBestPairing(groupPlayers);
    const pairScore = pairingResult.score;

    // คนที่รอนาน: currentRound - lastPlayedRound
    const waitSum = groupPlayers.reduce(
      (sum, p) => sum + (currentRound - (p.lastPlayedRound || 0)),
      0
    );

    // รวมจำนวนเกมที่เคยเล่นของทั้งกลุ่ม
    const gamesSum = groupPlayers.reduce(
      (sum, p) => sum + p.gamesPlayed,
      0
    );

    // fairnessScore:
    //  - pairScore: เน้นกระจายคู่ / หลีกเลี่ยงคู่ที่เล่นกันบ่อย
    //  - waitSum: ดึงคนที่รอนาน
    //  - gamesSum: ลดถ้าเล่นเยอะแล้ว
    const fairnessScore =
      pairScore * 10 +
      waitSum * 2 -
      gamesSum;

    const jitter = Math.random();

    if (
      !bestOption ||
      fairnessScore > bestOption.fairnessScore ||
      (fairnessScore === bestOption.fairnessScore &&
        jitter > bestOption.jitter)
    ) {
      bestOption = {
        selectedPlayers: groupPlayers,
        pairs: pairingResult.pairs,
        fairnessScore,
        jitter
      };
    }
  });

  // เผื่อกรณีเงื่อนไขแน่นไปจนหา combo ไม่เจอเลย → fallback กลับไปไม่บังคับ minSat
  if (!bestOption) {
    const combosAll = combinations(allIds, COURT_SIZE);
    combosAll.forEach(comboIds => {
      const groupPlayers = comboIds.map(id => allPlayers.find(p => p.id === id));
      const pairingResult = selectBestPairing(groupPlayers);
      const pairScore = pairingResult.score;

      const waitSum = groupPlayers.reduce(
        (sum, p) => sum + (currentRound - (p.lastPlayedRound || 0)),
        0
      );
      const gamesSum = groupPlayers.reduce(
        (sum, p) => sum + p.gamesPlayed,
        0
      );

      const fairnessScore = pairScore * 10 + waitSum * 2 - gamesSum;
      const jitter = Math.random();

      if (
        !bestOption ||
        fairnessScore > bestOption.fairnessScore ||
        (fairnessScore === bestOption.fairnessScore &&
          jitter > bestOption.jitter)
      ) {
        bestOption = {
          selectedPlayers: groupPlayers,
          pairs: pairingResult.pairs,
          fairnessScore,
          jitter
        };
      }
    });
  }

  return bestOption;
}

// ==========================
// เลือกการจับคู่ในกลุ่ม 4 คน
//   - ลด "max pairCount" ก่อน (คู่ที่โดนจับบ่อยสุดใน pattern นี้)
//   - เพิ่มคู่ใหม่ / คู่น้อยครั้ง
// ==========================
function selectBestPairing(players4) {
  const patterns = [
    [ [0, 1], [2, 3] ],
    [ [0, 2], [1, 3] ],
    [ [0, 3], [1, 2] ]
  ];

  let best = null;

  patterns.forEach(pattern => {
    const pairs = [];
    const counts = [];

    pattern.forEach(([i, j]) => {
      const a = players4[i];
      const b = players4[j];
      const key = pairKey(a.id, b.id);
      const count = pairCount.get(key) || 0;
      pairs.push([a, b]);
      counts.push(count);
    });

    const maxCount = Math.max(...counts);
    const sumCount = counts.reduce((s, c) => s + c, 0);
    const newPairs = counts.filter(c => c === 0).length;

    // อยากได้ pattern ที่:
    // 1) maxCount น้อยที่สุด (ไม่มีคู่ไหนโดน spam)
    // 2) newPairs เยอะที่สุด
    // 3) sumCount น้อยที่สุด
    let score =
      -maxCount * 1000 +   // หลีกเลี่ยงคู่ที่เล่นกันบ่อยที่สุดก่อน
      newPairs * 50 -
      sumCount * 5;

    const jitter = Math.random();
    score += jitter; // กัน pattern เดิมซ้ำเมื่อคะแนนเท่ากันพอดี

    if (!best || score > best.score) {
      best = { pairs, score };
    }
  });

  return best;
}

// ==========================
// สร้าง combinations k ตัวจาก array
// ==========================
function combinations(arr, k) {
  const result = [];
  const n = arr.length;

  function backtrack(start, path) {
    if (path.length === k) {
      result.push([...path]);
      return;
    }
    for (let i = start; i < n; i++) {
      path.push(arr[i]);
      backtrack(i + 1, path);
      path.pop();
    }
  }

  backtrack(0, []);
  return result;
}

// ==========================
// แสดงผลรอบ
// ==========================
function renderRound(roundNo, selectedPlayers, pairs) {
  const names = selectedPlayers.map(p => p.name);
  roundInfoDiv.textContent = `รอบที่ ${roundNo}: ลงเล่น = ${names.join(', ')}`;

  let html = '';
  pairs.forEach((pair, idx) => {
    html += `คู่ที่ ${idx + 1}: ${pair[0].name} 🤝 ${pair[1].name}<br>`;
  });
  pairInfoDiv.innerHTML = html;
}
