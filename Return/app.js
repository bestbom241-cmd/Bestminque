function hello(username,lastname) 
{           
    return "Hello " + username + "" + lastname + " !"
}
function getage()
{
    return 24
}
let name = prompt("Enter your name: ")
let lastname = prompt("Enter your lastname: ")
alert(hello(name," "+lastname))