import random
import time
import numpy as np
import numba
from numba import njit, prange

###################################################################

# PLayer 0 => Vertical    Player
# PLayer 1 => Horizontal  Player

# player_id   : id player 0/1

# x,y : coordonnées de la tuile, Player0 joue sur (x,y)+(x,y+1) et Player1 sur (x,y)+(x+1,y)

# convert: player,x,y <=> IDmove

# IDmove=123 <=> player 1 plays at position x = 2 and y = 3
# ce codage tient sur 8 bits !


@njit
def get_id_move(player_id: int, coordinate_x: int, coordinate_y: int) -> int:
    """
    Take the player ID (0 for the vertical player, 1 for the horizontal player)
    and return the encoded move id at (coordinate_x, coordinate_y)
    """
    return player_id * 100 + coordinate_x * 10 + coordinate_y


@njit
def decode_id_move(id_move: int) -> tuple[int, int, int]:
    """
    Take a move id and decode it
    return:
        the player that have played it (0 for the vertical player, 1 for the horizontal player),
        the move coordinate (x and y)
    """
    coordinate_y: int = id_move % 10
    coordinate_x: int = int(id_move / 10) % 10
    player_id: int = int(id_move / 100)
    return player_id, coordinate_x, coordinate_y


###################################################################

# Numba requiert des numpy array pour fonctionner

# toutes les données du jeu sont donc stockées dans 1 seul array numpy

# Data Structure  - numpy array de taille 144 uint8 :
# B[0 - 63] List of possibles moves
# B[64-127] Gameboard (x,y) => 64 + x + 8*y
# B[-1] : number of possible moves // game is over
# B[-2] : reserved
# B[-3] : current player


starting_board = np.zeros(144, dtype=np.uint8)


@njit
def ip_xy(coordinate_x: int, coordinate_y: int) -> int:
    """
    convert (x, y) coordinate into array index
    return board indice of encoded coordinate
    """
    return 64 + 8 * coordinate_y + coordinate_x


@njit
def _possible_moves(player_id: int, board: np.ndarray) -> None:
    """
    update the board for the current player, to set his possible moves
    (player_id = 0 => vertical player, player_id = 1 => horizontal player)
    update the count of possible move
    """
    count: int = 0

    # player V
    if player_id == 0:
        for coordinate_x in range(8):
            for coordinate_y in range(7):
                player = ip_xy(coordinate_x, coordinate_y)
                if board[player] == 0 and board[player + 8] == 0:
                    board[count] = get_id_move(0, coordinate_x, coordinate_y)
                    count += 1
    # player H
    if player_id == 1:
        for coordinate_x in range(7):
            for coordinate_y in range(8):
                player = ip_xy(coordinate_x, coordinate_y)
                if board[player] == 0 and board[player + 1] == 0:
                    board[count] = get_id_move(1, coordinate_x, coordinate_y)
                    count += 1
    board[-1] = count


_possible_moves(0, starting_board)  # prépare le gameboard de démarrage

###################################################################

# Numba ne gère pas les classes...

# fonctions de gestion d'une partie
# les fonctions sans @jit ne sont pas accélérées

# Player 0 win => Score :  1
# Player 1 win => Score : -1


@njit
def terminated(board: np.ndarray) -> bool:
    """
    return true if the game is over
    else false
    """
    return board[-1] == 0


@njit
def get_score(board: np.ndarray) -> int:
    """
    return the current game winner
    """
    if board[-2] == 10:
        return 1
    if board[-2] == 20:
        return -1
    return 0


@njit
def play(board: np.ndarray, id_move: int) -> None:
    """
    play one turn of the game
    id_move can be decoded to find the player, and the coordinate of the move
    """
    player, coordinate_x, coordinate_y = decode_id_move(id_move)
    player_id: int = ip_xy(coordinate_x, coordinate_y)

    board[player_id] = 1
    if player == 0:
        board[player_id + 8] = 1
    else:
        board[player_id + 1] = 1
    next_player = 1 - player

    _possible_moves(next_player, board)
    board[-3] = next_player

    if board[-1] == 0:  # gameover
        # player 0 win => 10  / player 1 win => 20
        board[-2] = (player + 1) * 10


@njit
def playout(board: np.ndarray, move_id: int) -> None:
    """
    play an entire game
    """
    while not terminated(board):  # play the game
        play_id: int = board[move_id]
        play(board, play_id)


@njit
def playout_random(board: np.ndarray) -> None:
    """
    play an entire game with random move
    """
    while not terminated(board):
        move_id: int = random.randint(0, board[-1] - 1)
        play_id: int = board[move_id]
        play(board, play_id)


@njit
def pvp_one_match(nog_player_0: int, nog_player_1: int, p=False) -> int:
    """
    play a full match between two ia
    depending on the current player, change simulation parameters
    """
    board: np.ndarray = starting_board.copy()
    while not terminated(board):
        if board[-3] == 0:
            nog: int = nog_player_0
        else:
            nog: int = nog_player_1
        best_move: int = find_best_move(board, nog, p)
        play_id: int = board[best_move]
        play(board, play_id)
    return get_score(board)


@njit
def pvp_multiple_match(
    number_of_game: int, nog_player_0: int, nog_player_1: int, p=False
) -> np.ndarray:
    """
    play 'number of game' game between two ia
    return a ndarray where arr[i] = Player_i number of win, i ∈ {0, 1}
    """
    win_count: np.ndarray = np.zeros(2)
    for _ in range(number_of_game):
        winner: int = pvp_one_match(nog_player_0, nog_player_1, p=p)
        if winner == 1:
            win_count[0] += 1
        else:
            win_count[1] += 1
    return win_count


@njit
def simulate_random_game(board: np.ndarray, move_id: int) -> np.ndarray:
    copied: np.ndarray = board.copy()
    play_id: int = copied[move_id]
    play(copied, play_id)
    playout_random(copied)
    return copied


@njit(parallel=True)
def find_best_move(board: np.ndarray, number_of_game: int, p=False) -> int:
    """
    simulate 'number_of_game' game per move for the two ia to chose the best move
    return the best move to play for the current ia
    """
    possible_moves_count: int = board[-1]
    means: np.ndarray = np.zeros(possible_moves_count, dtype=np.float64)
    current_player: int = board[-3]
    for move_id in range(0, possible_moves_count):  # check all the possible move
        scores: np.ndarray = np.zeros(number_of_game, dtype=np.int32)
        if p == True:
            for game in prange(0, number_of_game):
                copied: np.ndarray = simulate_random_game(board, number_of_game)
                scores[game] = get_score(
                    copied
                )  # update the score for the game that just ended
        else:
            for game in range(0, number_of_game):
                copied: np.ndarray = simulate_random_game(board, number_of_game)
                scores[game] = get_score(
                    copied
                )  # update the score for the game that just ended
        means[move_id] = scores.mean()
    if current_player == 1:
        return int(np.argmin(means))
    return int(np.argmax(means))


#   for demo only - do not use for computation
def custom_print(board: np.ndarray) -> None:
    """
    custom print function to print the board
    represented as a numpy nd array
    """
    print(board)
    for yy in range(8):
        y = 7 - yy
        string_container = str(y)
        for coordinate_x in range(8):
            if board[ip_xy(coordinate_x, y)] == 1:
                string_container += "::"
            else:
                string_container += "[]"
        print(string_container)
    string_container = " "
    for coordinate_x in range(8):
        string_container += str(coordinate_x) + str(coordinate_x)
    print(string_container)

    nb_moves = board[-1]
    print(f"Possible moves : {nb_moves}")
    string_container = ""
    for i in range(nb_moves):
        string_container += str(board[i]) + " "
    print(string_container)


def playout_debug(board: np.ndarray) -> None:
    """
    play a full game in debugging mode
    """
    custom_print(board)
    while not terminated(board):
        id = random.randint(0, board[-1] - 1)
        id_move = board[id]
        player_id, coordinate_x, coordinate_y = decode_id_move(id_move)
        print(
            f"Playing : {id_move} - Player: {player_id}  X: {coordinate_x}  Y: {coordinate_y}"
        )
        play(board, id_move)
        custom_print(board)
        print("---------------------------------------")


################################################################
#
#  Version Debug Demo pour affichage et test


@njit(parallel=True)
def parrallel_playout(number: int):
    """
    play a full game in parra mode with numba
    """
    scores = np.empty(number)
    for i in numba.prange(number):
        board = starting_board.copy()
        playout_random(board)
        scores[i] = get_score(board)
    return scores.mean()


def numba_main() -> None:
    """
    main function for the numba playout
    can play at least 100 000 game per second
    """

    print("Test perf Numba")

    T0 = time.time()
    number_of_simulations = 0
    while time.time() - T0 < 2:
        board = starting_board.copy()
        playout_random(board)
        number_of_simulations += 1
    print(f"Nb Sims / second: {number_of_simulations / 2}")


def numba_parra_main() -> None:
    """
    main function for the parra of for the numba playout
    can play at least 300 000 game per second
    """
    print("Test perf Numba + parallélisme")

    number_of_simulations = 10 * 1000 * 1000
    T0 = time.time()
    mean_scores = parrallel_playout(number_of_simulations)
    T1 = time.time()
    dt = T1 - T0

    print(f"Nb Sims / second:, {(number_of_simulations / dt)}")


def main_pvp() -> None:
    """
    main function for ia vs ia matchs
    """
    number_of_game: int = 10
    ia100p: int = 100
    ia1000p: int = 1000
    ia10000p: int = 10000
    score_100_100: np.ndarray = pvp_multiple_match(
        number_of_game, nog_player_0=ia100p, nog_player_1=ia100p
    )
    score_100_1000: np.ndarray = pvp_multiple_match(
        number_of_game, nog_player_0=ia100p, nog_player_1=ia1000p, p=True
    )
    score_100_10000: np.ndarray = pvp_multiple_match(
        number_of_game, nog_player_0=ia100p, nog_player_1=ia10000p
    )
    print(get_score_string(score_100_100, number_of_game))
    print(get_score_string(score_100_1000, number_of_game))
    print(get_score_string(score_100_10000, number_of_game))


def get_score_string(score: np.ndarray, number_of_game: int) -> str:
    return f"{(score[0] / number_of_game) * 100}% Win IA 1 - {(score[1] / number_of_game) * 100}% Win IA 2"


def main() -> None:
    """
    main function for our programm
    """
    main_pvp()


if __name__ == "__main__":
    main()