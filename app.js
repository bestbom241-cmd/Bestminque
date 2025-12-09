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
//   1) เน้นคู่ใหม่ / คู่ที่ยังไม่ค่อยได้คู่กัน
//   2) ดึงคนที่รอนาน / เล่นน้อยขึ้นมาก่อน
// ==========================
function createNextRound() {
  const currentRound = roundNumber + 1;
  const allPlayers = [...players];
  const allIds = allPlayers.map(p => p.id);

  let bestOption = null;
  const combos = combinations(allIds, COURT_SIZE);

  combos.forEach(comboIds => {
    const groupPlayers = comboIds.map(id => allPlayers.find(p => p.id === id));

    // เลือกการจับคู่ที่ดีที่สุดใน 4 คนนี้ (ดู pairCount ด้วย)
    const pairingResult = selectBestPairing(groupPlayers);
    const pairScore = pairingResult.score;

    // คนที่รอนาน (รอบปัจจุบัน - รอบที่เล่นล่าสุด)
    const waitSum = groupPlayers.reduce(
      (sum, p) => sum + (currentRound - (p.lastPlayedRound || 0)),
      0
    );

    // รวมจำนวนเกมที่เคยเล่นของทั้งกลุ่ม
    const gamesSum = groupPlayers.reduce(
      (sum, p) => sum + p.gamesPlayed,
      0
    );

    // คนที่ "ไม่" อยู่ในรอบที่แล้ว (คือคนนั่งเมื่อกี้)
    const numSatLastRound = groupPlayers.filter(
      p => !lastRoundPlayingIds.includes(p.id)
    ).length;

    // คะแนนรวม:
    //  - pairScore: กระจายคู่, เลี่ยงคู่ที่เล่นกันบ่อย
    //  - waitSum: ให้คนที่รอนานได้ลง
    //  - numSatLastRound: ถ้าเพิ่งนั่งรอบที่แล้ว จะมีน้ำหนักเพิ่ม
    //  - gamesSum: ถ้าเคยเล่นเยอะแล้ว จะโดนหักคะแนนหน่อย
    const fairnessScore =
      pairScore * 10 +        // เน้น pattern คู่ก่อนสุด
      waitSum * 3 +
      numSatLastRound * 20 -
      gamesSum;

    // random นิด ๆ กันแพทเทิร์นแข็งเกิน
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

  return bestOption;
}

// ==========================
// เลือกการจับคู่ในกลุ่ม 4 คน
//   - ถ้ามีคู่ใหม่ → ให้คะแนนสูง
//   - ถ้าต้องใช้คู่เดิม → ใช้คู่ที่เล่นกันน้อยรอบกว่า
// ==========================
function selectBestPairing(players4) {
  const patterns = [
    [ [0, 1], [2, 3] ],
    [ [0, 2], [1, 3] ],
    [ [0, 3], [1, 2] ]
  ];

  let best = null;

  patterns.forEach(pattern => {
    let newPairs = 0;
    let repeatPairs = 0;
    let sumPairCount = 0;
    let maxPairCount = 0;
    const pairs = [];

    pattern.forEach(([i, j]) => {
      const a = players4[i];
      const b = players4[j];
      const key = pairKey(a.id, b.id);
      const count = pairCount.get(key) || 0;

      if (count === 0) {
        newPairs++;
      } else {
        repeatPairs++;
      }

      sumPairCount += count;
      if (count > maxPairCount) maxPairCount = count;

      pairs.push([a, b]);
    });

    // คิดคะแนน pattern นี้
    //  - newPairs เยอะ = ดีมาก
    //  - sumPairCount / maxPairCount เยอะ = แปลว่าคู่นี้เคยเล่นด้วยกันบ่อย → หักคะแนน
    //  - repeatPairs = แค่จำนวนคู่ที่ไม่ใช่คู่ใหม่
    const score =
      newPairs * 200 -       // ดันคู่ใหม่เต็มที่
      sumPairCount * 15 -    // ถ้าคู่นี้เคยเล่นกันหลายรอบแล้ว หักหนักหน่อย
      maxPairCount * 10 -
      repeatPairs * 5;

    const jitter = Math.random(); // กันเท่ากันแล้วเลือก pattern แรกซ้ำ

    if (
      !best ||
      score > best.score ||
      (score === best.score && jitter > best.jitter)
    ) {
      best = { pairs, score, jitter };
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
