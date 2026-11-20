using ChessChallenge.API;

// Guard the original bot's scripted opening on FENs with partial move history.
internal static class BongcloudOpening
{
    internal static bool TryChoose(Board board, out Move chosen)
    {
        string? opening = board.PlyCount switch
        {
            0 => "e2e4",
            1 => "e7e5",
            2 => "e1e2",
            3 => "e8e7",
            _ => null,
        };
        chosen = default;
        if (opening == null) return false;

        var legal = board.GetLegalMoves();
        if (legal.Length == 0) return false;
        foreach (Move move in legal)
        {
            if (move.StartSquare.Name + move.TargetSquare.Name != opening) continue;
            chosen = move;
            return true;
        }

        // Preserve the bot's usual priorities when its scripted square is unavailable.
        foreach (Move move in legal)
        {
            if (move.IsCapture || move.IsPromotion)
            {
                chosen = move;
                return true;
            }
            board.MakeMove(move);
            bool mate = board.IsInCheckmate();
            board.UndoMove(move);
            if (mate)
            {
                chosen = move;
                return true;
            }
        }
        chosen = legal[Random.Shared.Next(legal.Length)];
        return true;
    }
}
