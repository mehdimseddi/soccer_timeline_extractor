// src/components/TeamLineup.tsx
import type { Player, PlayerPosition, Team } from "@/types/match";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type TeamLineupProps = {
  homeTeam: Team;
  awayTeam: Team;
  players: Player[]; // mixed, will be split by team name
};

const POSITION_GROUPS: Array<{
  key: "goalkeeper" | "defense" | "midfield" | "attack" | "unknown";
  label: string;
  positions: PlayerPosition[];
}> = [
    {
      key: "goalkeeper",
      label: "Goalkeeper",
      positions: ["goalkeeper"],
    },
    {
      key: "defense",
      label: "Defense",
      positions: ["right_back", "center_back", "left_back"],
    },
    {
      key: "midfield",
      label: "Midfield",
      positions: [
        "defensive_midfielder",
        "central_midfielder",
        "attacking_midfielder",
      ],
    },
    {
      key: "attack",
      label: "Attack",
      positions: ["right_winger", "left_winger", "striker", "second_striker"],
    },
    {
      key: "unknown",
      label: "Unassigned",
      positions: [],
    },
  ];

function splitByTeam(players: Player[], teamName: string) {
  return players.filter((p) => p.team === teamName);
}

function groupByPosition(players: Player[]): Record<string, Player[]> {
  const groups: Record<string, Player[]> = {
    goalkeeper: [],
    defense: [],
    midfield: [],
    attack: [],
    unknown: [],
  };

  for (const player of players) {
    if (!player.position) {
      groups.unknown.push(player);
      continue;
    }
    const pos = player.position;
    const bucket = POSITION_GROUPS.find((g) => g.positions.includes(pos));
    if (!bucket) {
      groups.unknown.push(player);
    } else {
      groups[bucket.key].push(player);
    }
  }

  // Stable, readable ordering within lines: keep input order as-is
  return groups;
}

function TeamCard({ team, players }: { team: Team; players: Player[] }) {
  const grouped = groupByPosition(players);

  return (
    <Card>
      <CardHeader className="flex flex-col items-center gap-2">
        {team.logo ? (
          <img
            src={team.logo}
            alt={team.name}
            className="w-8 h-8 sm:w-12 sm:h-12 md:w-14 md:h-14 object-contain"
          />
        ) : (
          <span className="text-xs font-semibold">{team.name.charAt(0)}</span>
        )}
        <CardTitle className="text-base sm:text-lg text-center truncate">
          {team.name}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {POSITION_GROUPS.map(({ key, label }) => {
          const line = grouped[key] || [];
          if (line.length === 0) return null;
          return (
            <div key={key} className="space-y-1.5">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
              <div className="flex flex-wrap gap-1.5">
                {line.map((p, idx) => (
                  <Badge key={`${p.name}-${idx}`} variant="outline" className="flex items-center gap-1">
                    {p.number != null && (
                      <span className="tabular-nums text-xs text-muted-foreground">#{p.number}</span>
                    )}
                    <span className="truncate max-w-[12rem]">{p.name}</span>
                  </Badge>
                ))}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function TeamLineup({ homeTeam, awayTeam, players }: TeamLineupProps) {
  const homePlayers = splitByTeam(players, homeTeam.name);
  const awayPlayers = splitByTeam(players, awayTeam.name);

  const hasAny = homePlayers.length > 0 || awayPlayers.length > 0;

  if (!hasAny) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Lineups</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No lineup data available.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Lineups</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="list" className="w-full">
          <TabsList className="grid w-full max-w-sm grid-cols-2 mx-auto">
            <TabsTrigger value="list">List</TabsTrigger>
            <TabsTrigger value="formation">Formation</TabsTrigger>
          </TabsList>

          <TabsContent value="list" className="mt-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <TeamCard team={homeTeam} players={homePlayers} />
              <TeamCard team={awayTeam} players={awayPlayers} />
            </div>
          </TabsContent>

          <TabsContent value="formation" className="mt-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <TeamPitch team={homeTeam} players={homePlayers} />
              <TeamPitch team={awayTeam} players={awayPlayers} />
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function TeamPitch({ team, players }: { team: Team; players: Player[] }) {
  const grouped = groupByPosition(players);

  // Derive a simple formation string e.g., 4-3-3 or 4-2-3-1 based on counts
  const defenseCount = grouped.defense.length || 0;
  const midfieldCount = grouped.midfield.length || 0;
  const attackCount = grouped.attack.length || 0;

  const derivedFormation = `${Math.max(defenseCount, 0)}-${Math.max(midfieldCount, 0)}-${Math.max(attackCount, 0)}`;

  // Helper to render a line centered with even spacing
  const LineRow = ({ line }: { line: Player[] }) => (
    <div className="flex justify-center gap-2 flex-wrap">
      {line.length === 0 ? (
        <span className="text-xs text-muted-foreground">—</span>
      ) : (
        line.map((p, idx) => (
          <Badge key={`${p.name}-${idx}`} variant="secondary" className="bg-white/80 dark:bg-white/10 flex items-center gap-1">
            {p.number != null && (
              <span className="tabular-nums text-xs text-foreground/70">#{p.number}</span>
            )}
            <span className="truncate max-w-[9rem]">{p.name}</span>
          </Badge>
        ))
      )}
    </div>
  );

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          {team.logo ? (
            <img src={team.logo} alt={team.name} className="w-8 h-8 sm:w-12 sm:h-12 md:w-14 md:h-14 object-contain" />
          ) : (
            <span className="text-xs font-semibold">{team.name.charAt(0)}</span>
          )}
          <CardTitle className="text-base sm:text-lg truncate">{team.name}</CardTitle>
        </div>
        <div className="text-xs text-muted-foreground">{derivedFormation}</div>
      </CardHeader>
      <CardContent>
        <div
          className="relative rounded-lg p-3 sm:p-4"
          style={{
            background:
              "repeating-linear-gradient(0deg, rgba(16,94,50,1) 0, rgba(16,94,50,1) 36px, rgba(12,77,41,1) 36px, rgba(12,77,41,1) 72px)",
          }}
        >
          {/* Pitch markings */}
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute inset-2 border border-white/50 rounded-md" />
            <div className="absolute left-1/2 top-2 bottom-2 w-px bg-white/50 -translate-x-1/2" />
          </div>

          <div className="relative z-10 grid grid-rows-5 gap-4 sm:gap-6">
            {/* Attack */}
            <LineRow line={grouped.attack} />
            {/* Midfield */}
            <LineRow line={grouped.midfield} />
            {/* Defense */}
            <LineRow line={grouped.defense} />
            {/* GK */}
            <div className="flex justify-center">
              <LineRow line={grouped.goalkeeper} />
            </div>
            {/* Unassigned bench */}
            {grouped.unknown.length > 0 && (
              <div className="flex justify-center">
                <Badge variant="outline" className="bg-white/70 dark:bg-white/5">Bench</Badge>
                <div className="ml-2 flex flex-wrap gap-1.5">
                  {grouped.unknown.map((p, idx) => (
                    <Badge key={`${p.name}-bench-${idx}`} variant="outline" className="bg-white/70 dark:bg-white/5">
                      <span className="truncate max-w-[9rem]">{p.name}</span>
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
