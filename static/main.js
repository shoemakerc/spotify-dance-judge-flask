/*
var searchTracks = function (query, access_token) {
  $.ajax({
    url: 'https://api.spotify.com/v1/search',
    headers: {
      'Authorization': 'Bearer ' + access_token
    },
    data: {
      q: query,
      type: 'track',
      market: 'US',
      limit: 1
    },
    success: function (response) {
      var templateSource = document.getElementById('results-template').innerHTML,
          template = Handlebars.compile(templateSource),
          resultsPlaceholder = document.getElementById('results');
      resultsPlaceholder.innerHTML = template(response);
      getAudioFeatures(response.tracks.items[0].id, access_token);
    }
  });
};

var getAudioFeatures = function(id, access_token) {
  $.ajax({
    url: 'https://api.spotify.com/v1/audio-features/' + id,
    headers: {
      'Authorization': 'Bearer ' + access_token
    },
    success: function(response) {
      var audioFeaturesSource = document.getElementById('audio-features-template').innerHTML,
          audioFeaturesTemplate = Handlebars.compile(audioFeaturesSource),
          audioFeaturesPlaceholder = document.getElementById('audio-features');
      audioFeaturesPlaceholder.innerHTML = audioFeaturesTemplate(response);
    }
  });
};
*/
function getHashParams() {
  /**
    * Obtains parameters from the hash of the URL
    * @return {Object} The parameters from the hash
    */
  var hashParams = {};
  var e, r = /([^&;=]+)=?([^&;]*)/g,
    q = window.location.hash.substring(1);
  while ( e = r.exec(q)) {
    hashParams[e[1]] = decodeURIComponent(e[2]);
  }
  return hashParams;
};