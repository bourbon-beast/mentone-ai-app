// functions/lib/index.js
const functions = require('firebase-functions');

exports.helloWorld = functions.https.onRequest((request, response) => {
    response.send("Hello from Mentone Hockey Club!");
});