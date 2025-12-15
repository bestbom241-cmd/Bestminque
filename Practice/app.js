function toCelsius(fahrenheit)
{
    let value = (fahrenheit - 32) * 5 / 9;
    return value.toFixed(2) + " °C";
}

function toFahrenheit(celsius)
{
    let value = (celsius * 9) / 5 + 32;
    return value.toFixed(2) + " °F";
}

function display(elementId, value)
{
    document.getElementById(elementId).innerHTML = "<b>" + value + "</b>";
}

function toCelsiusProgram(value)
{
    let result = toCelsius(value);
    display("toCelsius", result);
}

function toFahrenheitProgram(value)
{
    let result = toFahrenheit(value);
    display("toFahrenheit", result);
}
