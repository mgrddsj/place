const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 8081 });
 
var dim = 250; // note: this is not the right dimensions!!
// A simple list of paint events so new clients can replay it.
const history = [];

wss.on('close', function() {
    console.log('disconnected');
});

wss.broadcast = function broadcast(data) {
  wss.clients.forEach(function each(client) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(data);
    }
  });
};

// for heartbeat to make sure connection is alive 
function noop() {}
function heartbeat() {
  this.isAlive = true;
}

function isValidSet(o){
	var isValid=false;
	try {
	   isValid = 
		Number.isInteger(o.x) && o.x!=null && 0<=o.x && o.x<dim &&
		Number.isInteger(o.y) && o.y!=null && 0<=o.y && o.y<dim && 
		Number.isInteger(o.r) && o.r!=null && 0<=o.r && o.r<=255 && 
		Number.isInteger(o.g) && o.g!=null && 0<=o.g && o.g<=255 && 
		Number.isInteger(o.b) && o.b!=null && 0<=o.b && o.b<=255;
	} catch (err){ 
		isValid=false; 
	} 
	return isValid;
}
wss.on('connection', function(ws) {
	// heartbeat
  	ws.isAlive = true;
  	ws.on('pong', heartbeat);

	// send complete history so the client catches up
	history.forEach((event) => ws.send(event));

	// when we get a message from the client
	ws.on('message', function(message) {
		console.log(message);
		var o = JSON.parse(message);
		if(isValidSet(o)){
			const serialized = JSON.stringify(o);
			history.push(serialized);
			wss.broadcast(serialized);
		}
	});
});

// heartbeat (ping) sent to all clients
const interval = setInterval(function ping() {
  wss.clients.forEach(function each(ws) {
    if (ws.isAlive === false) return ws.terminate();
 
    ws.isAlive = false;
    ws.ping(noop);
  });
}, 30000);
