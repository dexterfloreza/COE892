from utils.rover import Rover
from utils.detect_mines import find_mine_pins_using_threads


def create_rover() -> Rover:
    rover_number = int(input("Enter rover number: "))
    rover_name = f"Rover {rover_number}"

    return Rover(
        rover_name,
        rover_number,
        is_part_2=True,
        dig_mine_function=find_mine_pins_using_threads
    )


def main():
    rover = create_rover()
    rover.start_rover()


if __name__ == "__main__":
    main()