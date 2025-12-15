const panel = document.getElementById("content");

if (panel) {
  const response = prompt("How old are you?");
  const age = response ? parseInt(response.trim(), 10) : NaN;

  if (Number.isNaN(age)) {
    panel.innerHTML = `
      <h2>Age Required</h2>
      <p>Please refresh the page and enter a valid number.</p>
    `;
  } else if (age < 18) {
    panel.innerHTML = `
      <h2>Access Denied</h2>
      <p>This website is for users aged 18 and above.</p>
    `;
  } else {
    panel.innerHTML = `
      <h2>Welcome</h2>
      <p>You are verified as an adult. Continue by clicking the button below.</p>
    `;
  }
}
