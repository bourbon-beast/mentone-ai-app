import React, { useState } from 'react';

function AdminPanel() {
  // State for Discover Competitions
  const [discoverCompetitionsLoading, setDiscoverCompetitionsLoading] = useState(false);
  const [discoverCompetitionsMessage, setDiscoverCompetitionsMessage] = useState('');

  // State for Discover Games
  const [discoverGamesLoading, setDiscoverGamesLoading] = useState(false);
  const [discoverGamesMessage, setDiscoverGamesMessage] = useState('');

  // State for Discover Players
  const [discoverPlayersLoading, setDiscoverPlayersLoading] = useState(false);
  const [discoverPlayersMessage, setDiscoverPlayersMessage] = useState('');

  // State for Discover Teams
  const [discoverTeamsLoading, setDiscoverTeamsLoading] = useState(false);
  const [discoverTeamsMessage, setDiscoverTeamsMessage] = useState('');

  // State for Extract Venues
  const [extractVenuesLoading, setExtractVenuesLoading] = useState(false);
  const [extractVenuesMessage, setExtractVenuesMessage] = useState('');

  // State for Update Ladder
  const [updateLadderLoading, setUpdateLadderLoading] = useState(false);
  const [updateLadderMessage, setUpdateLadderMessage] = useState('');

  // State for Update Results
  const [updateResultsLoading, setUpdateResultsLoading] = useState(false);
  const [updateResultsMessage, setUpdateResultsMessage] = useState('');

  const getBaseUrl = () => {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://127.0.0.1:5001/hockey-tracker-e67d0/us-central1'; // Emulator URL
    }
    return 'https://us-central1-hockey-tracker-e67d0.cloudfunctions.net'; // Deployed URL
  };

  const handleDiscoverCompetitions = async () => {
    setDiscoverCompetitionsLoading(true);
    setDiscoverCompetitionsMessage('');
    const functionUrl = `${getBaseUrl()}/discover_competitions`;
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setDiscoverCompetitionsMessage(`Success: ${data.message || 'Competitions discovered.'} (Found: ${data.data?.competitions_found || 0}, Saved: ${data.data?.competitions_saved || 0})`);
    } catch (error) {
      setDiscoverCompetitionsMessage(`Error: ${error.message}`);
    } finally {
      setDiscoverCompetitionsLoading(false);
    }
  };

  const handleDiscoverGames = async () => {
    setDiscoverGamesLoading(true);
    setDiscoverGamesMessage('');
    const functionUrl = `${getBaseUrl()}/discover_games?mentone_only=true&limit_teams=0`; // Example: Fetch all Mentone teams fixtures
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setDiscoverGamesMessage(`Success: ${data.message || 'Games discovered.'} (Found: ${data.data?.games_found_total || 0}, Saved: ${data.data?.games_saved_total || 0})`);
    } catch (error) {
      setDiscoverGamesMessage(`Error: ${error.message}`);
    } finally {
      setDiscoverGamesLoading(false);
    }
  };

  const handleDiscoverPlayers = async () => {
    setDiscoverPlayersLoading(true);
    setDiscoverPlayersMessage('');
    const functionUrl = `${getBaseUrl()}/discover_players?mentone_only=true&limit_teams=0`; // Example: Process all Mentone teams
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setDiscoverPlayersMessage(`Success: ${data.message || 'Players discovered.'} (Players Updated: ${data.data?.unique_players_saved_or_updated || 0})`);
    } catch (error) {
      setDiscoverPlayersMessage(`Error: ${error.message}`);
    } finally {
      setDiscoverPlayersLoading(false);
    }
  };

  const handleDiscoverTeams = async () => {
    setDiscoverTeamsLoading(true);
    setDiscoverTeamsMessage('');
    const functionUrl = `${getBaseUrl()}/discover_teams`; // Default: all active grades, Mentone teams identified
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setDiscoverTeamsMessage(`Success: ${data.message || 'Teams discovered.'} (Teams Found: ${data.data?.teams_found || 0}, Mentone Saved: ${data.data?.mentone_teams_saved_or_dryrun || 0})`);
    } catch (error) {
      setDiscoverTeamsMessage(`Error: ${error.message}`);
    } finally {
      setDiscoverTeamsLoading(false);
    }
  };

  const handleExtractVenues = async () => {
    setExtractVenuesLoading(true);
    setExtractVenuesMessage('');
    const functionUrl = `${getBaseUrl()}/extract_venues?process_from_firestore=true&limit_games=25`; // Process some games from DB
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setExtractVenuesMessage(`Success: ${data.message || 'Venues extracted.'} (Venues Identified: ${data.data?.unique_venues_identified_in_run || 0})`);
    } catch (error) {
      setExtractVenuesMessage(`Error: ${error.message}`);
    } finally {
      setExtractVenuesLoading(false);
    }
  };

  const handleUpdateLadder = async () => {
    setUpdateLadderLoading(true);
    setUpdateLadderMessage('');
    const functionUrl = `${getBaseUrl()}/update_ladder?mentone_only=true`; // Update all Mentone teams
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setUpdateLadderMessage(`Success: ${data.message || 'Ladders updated.'} (Teams Updated: ${data.data?.teams_successfully_updated || 0})`);
    } catch (error) {
      setUpdateLadderMessage(`Error: ${error.message}`);
    } finally {
      setUpdateLadderLoading(false);
    }
  };

  const handleUpdateResults = async () => {
    setUpdateResultsLoading(true);
    setUpdateResultsMessage('');
    const functionUrl = `${getBaseUrl()}/update_results?days_back=7&limit_games=25`; // Update results for recent games
    try {
      const response = await fetch(functionUrl);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to parse error JSON' }));
        throw new Error(`Network error: ${response.status} ${response.statusText}. ${errorData.message || ''}`);
      }
      const data = await response.json();
      setUpdateResultsMessage(`Success: ${data.message || 'Results updated.'} (Games Updated: ${data.data?.games_updated_in_firestore || 0})`);
    } catch (error) {
      setUpdateResultsMessage(`Error: ${error.message}`);
    } finally {
      setUpdateResultsLoading(false);
    }
  };
  
  const commonButtonClasses = "bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded disabled:opacity-50 transition duration-150 ease-in-out";

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6 text-gray-800 dark:text-white">Admin Panel</h1>
      <p className="text-gray-600 dark:text-gray-300 mb-8">
        This panel allows triggering various backend administrative tasks. Use with caution.
      </p>

      {/* Discover Competitions Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Discover Competitions</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Scans Hockey Victoria for current/past competitions. One-time or seasonal setup.
        </p>
        <button onClick={handleDiscoverCompetitions} disabled={discoverCompetitionsLoading} className={commonButtonClasses}>
          {discoverCompetitionsLoading ? 'Running...' : 'Run Discover Competitions'}
        </button>
        {discoverCompetitionsMessage && (
          <p className={`mt-3 text-sm ${discoverCompetitionsMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {discoverCompetitionsMessage}
          </p>
        )}
      </div>

      {/* Discover Games Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Pull fixtures for all Mentone teams</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Scans Hockey Victoria for all games/fixtures for all known Mentone teams and saves them.
        </p>
        <button onClick={handleDiscoverGames} disabled={discoverGamesLoading} className={commonButtonClasses}>
          {discoverGamesLoading ? 'Running...' : 'Run Discover Games'}
        </button>
        {discoverGamesMessage && (
          <p className={`mt-3 text-sm ${discoverGamesMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {discoverGamesMessage}
          </p>
        )}
      </div>

      {/* Discover Players Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Update player records from games</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Scrapes player statistics from team and game pages on Hockey Victoria.
        </p>
        <button onClick={handleDiscoverPlayers} disabled={discoverPlayersLoading} className={commonButtonClasses}>
          {discoverPlayersLoading ? 'Running...' : 'Run Discover Players'}
        </button>
        {discoverPlayersMessage && (
          <p className={`mt-3 text-sm ${discoverPlayersMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {discoverPlayersMessage}
          </p>
        )}
      </div>

      {/* Discover Teams Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Rebuild Mentone team list</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Extracts team information from ladder pages for all grades Mentone participates in.
        </p>
        <button onClick={handleDiscoverTeams} disabled={discoverTeamsLoading} className={commonButtonClasses}>
          {discoverTeamsLoading ? 'Running...' : 'Run Discover Teams'}
        </button>
        {discoverTeamsMessage && (
          <p className={`mt-3 text-sm ${discoverTeamsMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {discoverTeamsMessage}
          </p>
        )}
      </div>

      {/* Extract Venues Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Extract venues from fixtures</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Scrapes game pages to find and save venue details (name, address, map).
        </p>
        <button onClick={handleExtractVenues} disabled={extractVenuesLoading} className={commonButtonClasses}>
          {extractVenuesLoading ? 'Running...' : 'Run Extract Venues'}
        </button>
        {extractVenuesMessage && (
          <p className={`mt-3 text-sm ${extractVenuesMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {extractVenuesMessage}
          </p>
        )}
      </div>

      {/* Update Ladder Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Pull live ladder standings</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Fetches current ladder positions and points for Mentone teams and updates Firestore.
        </p>
        <button onClick={handleUpdateLadder} disabled={updateLadderLoading} className={commonButtonClasses}>
          {updateLadderLoading ? 'Running...' : 'Run Update Ladder'}
        </button>
        {updateLadderMessage && (
          <p className={`mt-3 text-sm ${updateLadderMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {updateLadderMessage}
          </p>
        )}
      </div>

      {/* Update Results Section */}
      <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
        <h2 className="text-xl font-semibold mb-2 text-gray-700 dark:text-gray-300">Poll and update completed results</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Checks recent games and updates their scores and status (completed, forfeit, etc.) in Firestore.
        </p>
        <button onClick={handleUpdateResults} disabled={updateResultsLoading} className={commonButtonClasses}>
          {updateResultsLoading ? 'Running...' : 'Run Update Results'}
        </button>
        {updateResultsMessage && (
          <p className={`mt-3 text-sm ${updateResultsMessage.startsWith('Error') ? 'text-red-500' : 'text-green-500'}`}>
            {updateResultsMessage}
          </p>
        )}
      </div>

    </div>
  );
}

export default AdminPanel;
