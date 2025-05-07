// src/App.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import UpcomingGames from './components/UpcomingGames';
import TeamList from './components/TeamList';
import TeamDetailPage from './components/TeamDetailPage';
import TeamPerformance from './components/TeamPerformance';
import PlayerStats from './components/PlayerStats';
import WeeklySummary from './components/WeeklySummary';
import TravelPlanner from './components/TravelPlanner';
import VenueManager from './components/VenueManager';
import MyTeams from './components/MyTeams'; // Import the new MyTeams component
import { FavoritesProvider } from './context/FavoritesContext';
import './App.css';

function App() {
    return (
        <FavoritesProvider>
            <BrowserRouter>
                <Routes>
                    {/* Wrap all main routes in the Layout */}
                    <Route path="/" element={<Layout />}>
                        {/* Index route for "/" (UpcomingGames) */}
                        <Route index element={<UpcomingGames />} />
                        {/* Route for the Teams List */}
                        <Route path="teams" element={<TeamList />} />
                        {/* Route for a specific Team Detail Page */}
                        <Route path="teams/:teamId" element={<TeamDetailPage />} />
                        {/* Route for My Teams page */}
                        <Route path="my-teams" element={<MyTeams />} />
                        {/* Route for Performance */}
                        <Route path="performance" element={<TeamPerformance />} />
                        {/* Route for Player Stats */}
                        <Route path="players" element={<PlayerStats />} />
                        {/* Route for Weekly Summary */}
                        <Route path="summary" element={<WeeklySummary />} />
                        {/* Route for Travel Planner */}
                        <Route path="travel" element={<TravelPlanner />} />
                        {/* Route for Venue Manager */}
                        <Route path="venues" element={<VenueManager />} />
                    </Route>
                </Routes>
            </BrowserRouter>
        </FavoritesProvider>
    );
}

export default App;