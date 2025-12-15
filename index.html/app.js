const ticketNumber = prompt("Enter your ticket number:");
const prizeNumber = Math.floor(Math.random() * 10000);

const result = document.getElementById("result");
if (!ticketNumber) {
  result.textContent = `Prize number: ${prizeNumber}`;
} else if (Number(ticketNumber) === prizeNumber) {
  result.textContent = `Prize number: ${prizeNumber}. You win!`;
} else {
  result.textContent = `Prize number: ${prizeNumber}. Your ticket (${ticketNumber}) did not match.`;
}

console.log( 1 == '1' );
console.log( 1 != 2 );
