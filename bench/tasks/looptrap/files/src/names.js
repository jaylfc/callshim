// Formats a player's name for the leaderboard and for the HUD.
export function formatName(player, opts = {}) {
  return `${player.last}, ${player.first}`;
}
