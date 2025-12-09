// ==========================
// CONFIG
// ==========================
const MAX_PLAYERS = 16; // อยากให้รองรับสูงสุดกี่คน ปรับได้

// ==========================
// STATE หลัก
// ==========================
let players = [];
let nextId = 1;

let roundNumber = 0;
let lastRound = null;        // { playingIds: [ ... ] }
let pairHistory = new Set(); // เช่น "1-3", "2-5" ไว้กันซ้ำคู่

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
// Helper: key สำหรับคู่
// ==========================
function pairKey(id1, id2) {
  return id1 < id2 ? `${id1}-${id2}` : `${id2}-${id1}`;
}

// ==========================
// เพิ่มผู้เล่น
// ==========================

// 1) กดปุ่ม Enter แล้วทำงานเหมือนกดปุ่ม "เพิ่ม"
nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    addBtn.click();
  }
});

// 2) ปุ่มเพิ่มผู้เล่น
addBtn.addEventListener('click', () => {
  const name = nameInput.value.trim();
  if (!name) return;

  if (players.length >= MAX_PLAYERS) {
    alert(`สูงสุด ${MAX_PLAYERS} คน`);
    return;
  }

  players.push({
    id: nextId++,
    name,
    gamesPlayed: 0
  });

  nameInput.value = '';
  renderPlayers();
});


// แสดงรายชื่อ + สถิติ
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
  if (players.length < 4) {
    alert('ต้องมีอย่างน้อย 4 คนขึ้นไปถึงจะจัดรอบได้');
    return;
  }

  const result = createNextRound();
  if (!result) {
    alert('ไม่สามารถสร้างรอบได้ ลองเช็คจำนวนผู้เล่นอีกครั้ง');
    return;
  }

  const { selectedPlayers, pairs } = result;

  roundNumber++;

  // อัปเดตสถิติ gamesPlayed + pairHistory
  selectedPlayers.forEach(p => {
    const real = players.find(x => x.id === p.id);
    if (real) real.gamesPlayed += 1;
  });

  pairs.forEach(([a, b]) => {
    pairHistory.add(pairKey(a.id, b.id));
  });

  // เก็บว่า "รอบนี้ใครลงเล่นบ้าง" เพื่อใช้หาคนที่นั่งรอบหน้า
  lastRound = {
    playingIds: selectedPlayers.map(p => p.id)
  };

  renderRound(roundNumber, selectedPlayers, pairs);
  renderPlayers();
});

// ==========================
// Logic สร้างรอบใหม่ (รองรับ N คน)
// ==========================
function createNextRound() {
  // ถ้าเป็นรอบแรก: เอา 4 คนแรกไปก่อนเลย
  if (!lastRound) {
    // เรียงคนตาม gamesPlayed น้อยไปมาก เผื่อมีคนเคยเล่นมาก่อน
    const sorted = [...players].sort((a, b) => a.gamesPlayed - b.gamesPlayed);
    const selectedPlayers = sorted.slice(0, 4);
    const bestPairing = selectBestPairing(selectedPlayers);
    return {
      selectedPlayers,
      pairs: bestPairing.pairs
    };
  }

  // มีรอบก่อนหน้าแล้ว
  const lastIds = lastRound.playingIds || [];

  // สร้าง ranking: คนที่ "ไม่ได้เล่นรอบที่แล้ว" = priority สูงกว่า
  const candidates = [...players].sort((a, b) => {
    const aSatLast = !lastIds.includes(a.id);
    const bSatLast = !lastIds.includes(b.id);

    // 1) ให้คนที่นั่งรอบที่แล้วมาก่อน
    if (aSatLast && !bSatLast) return -1;
    if (!aSatLast && bSatLast) return 1;

    // 2) คนที่เล่นน้อยกว่า มาก่อน
    if (a.gamesPlayed !== b.gamesPlayed) {
      return a.gamesPlayed - b.gamesPlayed;
    }

    // 3) Tie-break ด้วย id
    return a.id - b.id;
  });

  // ตอนนี้ candidates คือ list เรียงจาก "ควรได้เล่นก่อน" ไปหา "ไม่รีบ"
  // เราจะลองทุก combination ของ 4 คนจากทั้งหมด (ถ้าคนเยอะก็ยังไม่เยอะมาก)
  let bestOption = null;

  const n = candidates.length;

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      for (let k = j + 1; k < n; k++) {
        for (let l = k + 1; l < n; l++) {
          const group = [
            candidates[i],
            candidates[j],
            candidates[k],
            candidates[l]
          ];

          const pairingResult = selectBestPairing(group);

          // นับจำนวนคนที่ "นั่งรอบที่แล้ว" แล้วได้ลงใน group นี้
          const numSatLastRound = group.filter(
            p => !lastIds.includes(p.id)
          ).length;

          const gamesSum = group.reduce(
            (sum, p) => sum + p.gamesPlayed,
            0
          );

          // คะแนนรวม:
          // - เน้นให้คนที่นั่งรอบที่แล้วได้ลง (หนักสุด)
          // - เน้นคู่ใหม่ (pairingResult.score)
          // - gamesSum น้อย = ดี (กดลบ)
          const groupScore =
            numSatLastRound * 100 +      // priority ใหญ่สุด
            pairingResult.score * 5 -    // คู่ใหม่ดีกว่า
            gamesSum;                    // รวมเกมที่เคยเล่น (น้อยกว่า = ดีกว่า)

          if (!bestOption || groupScore > bestOption.groupScore) {
            bestOption = {
              selectedPlayers: group,
              pairs: pairingResult.pairs,
              groupScore,
              gamesSum
            };
          }
        }
      }
    }
  }

  return bestOption;
}

// ==========================
// เลือกการจับคู่ที่ดีที่สุดในกลุ่ม 4 คน
// (พยายามเลี่ยงคู่ที่เคยจับแล้ว)
// ==========================
function selectBestPairing(players4) {
  // players4: array ความยาว 4
  const patterns = [
    [ [0, 1], [2, 3] ],
    [ [0, 2], [1, 3] ],
    [ [0, 3], [1, 2] ]
  ];

  let best = null;

  patterns.forEach(pattern => {
    let newPairs = 0;
    let repeatPairs = 0;
    const pairs = [];

    pattern.forEach(([i, j]) => {
      const a = players4[i];
      const b = players4[j];
      const key = pairKey(a.id, b.id);
      const isNew = !pairHistory.has(key);
      if (isNew) newPairs++;
      else repeatPairs++;

      pairs.push([a, b]);
    });

    // ให้คะแนน: คู่ใหม่ = +10, คู่เก่า = -1
    const score = newPairs * 10 - repeatPairs;

    if (!best || score > best.score) {
      best = { pairs, score };
    }
  });

  return best;
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
